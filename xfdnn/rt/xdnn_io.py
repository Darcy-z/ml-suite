##################################################
#Copyright (c) 2018, Xilinx, Inc.
#All rights reserved.
#
#Redistribution and use in source and binary forms, with or without modification,
#are permitted provided that the following conditions are met:
#
#1. Redistributions of source code must retain the above copyright notice,
#this list of conditions and the following disclaimer.
#
#2. Redistributions in binary form must reproduce the above copyright notice,
#this list of conditions and the following disclaimer in the documentation
#and/or other materials provided with the distribution.
#
#3. Neither the name of the copyright holder nor the names of its contributors
#may be used to endorse or promote products derived from this software
#without specific prior written permission.
#
#THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
#ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
#THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
#IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
#INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
#PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
#HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
#OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
#EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
##################################################

import numpy as np
import xdnn
import argparse
import os
import json
import math

def processCommandLine():
  parser = argparse.ArgumentParser(description='pyXDNN')
  parser.add_argument('--xclbin', required = True, 
    help='.xclbin file')
  parser.add_argument('--batch_sz', type=int, default = 1, 
    help='batch size')  
  parser.add_argument('--netcfg',
    help='FPGA instructions generated by compiler for the network')
  parser.add_argument('--quantizecfg', default = "",
    help='FPGA config file')
  parser.add_argument('--xlnxlib', required = True, 
    help='FPGA xfDNN lib .so')
  parser.add_argument('--fpgaoutsz', type=int, default = 1024, 
    help='size of 1 FPGA output blob')
  parser.add_argument('--outsz', type=int, default = 1000, 
    help='size of last layer\'s output blob')  
  parser.add_argument('--firstfpgalayer', default = "", 
    help='name of first FPGA layer (to start quantization)')
  parser.add_argument('--datadir',
    help='path to data files to run for the network')
  parser.add_argument('--labels', default = "",
    help='result -> labels translation file')
  parser.add_argument('--jsoncfg',
    help='json file with nets, data and PEs to use'),  
  parser.add_argument('--images', nargs='*',
    help='raw image files to use as input')
  parser.add_argument('--transform', type=str, default = 'resize',
    help='input image processing transform (i.e. resize, yolo, etc.')
  parser.add_argument('--scaleA', type=int, default = 10000, 
    help='weights scaling value')
  parser.add_argument('--scaleB', type=int, default = 30, 
    help='activation scaling value ')
  parser.add_argument('--img_mean', type=tuple, default = [104.007, 116.669, 122.679], # BGR for Caffe 
    help='image mean values ')
  parser.add_argument('--in_shape', type=str, default = [3, 224, 224], help='input dimensions')  
  parser.add_argument('--useblas', default = False, action='store_true',
    help='use BLAS-optimized functions (requires xfDNN lib compiled with BLAS)')
  parser.add_argument('--PE', nargs='?', type=int, default = -1,
    help='preferred PE to run the classification on. Default is auto-select')
  parser.add_argument('--blocking', nargs='?',
      help='use blocking calls. Default is blocking')    
  parser.add_argument('--endLayerName',default="",
      help='layer name till the network should be run, helpful for debugging')
  parser.add_argument('--diffStartLayer',type=int,default=0,
      help="if 1 then we can run from any given layer ignoring the X's of first layers")
  parser.add_argument('--v2WeightsFormat',type=int,default=0,
      help="Weights File specified as KernSizex KernSizey instead of only KernSize, supporting rectangle kernels")
  parser.add_argument('--layerName',default="",
      help='layername until which pyfpga should run, if left default, would run the entire model')
  parser.add_argument('--binaryFormatWeights',type=int,default=0,
      help="Binary Format Weights Files")
  args = parser.parse_args()
  args_dict = vars(args)
  
  if args_dict['images'] is not None and os.path.isdir( args_dict['images'][0] ):
    inputFiles = [os.path.join( args_dict['images'][0], f) \
    for f in os.listdir( args_dict['images'][0] ) if os.path.isfile( os.path.join( args_dict['images'][0], f))]
    args_dict['images'] = inputFiles
  
  if args_dict['jsoncfg']:
      fileName = args_dict['jsoncfg']
      args_dict['jsoncfg'] = args_dict
      with open(fileName) as jsoncfgFile:
          args_dict['jsoncfg'] = json.load(jsoncfgFile)['confs']
          new_args = []
          for dict_elem in args_dict['jsoncfg']:
              #if item.key
              #for key,value in dict_elem.items():
              for key,value in args_dict.items():
                  if key not in dict_elem:
                      dict_elem[key] = value
                      
              new_args.append(dict_elem)
           
          #print new_args
          args_dict['jsoncfg'] = new_args
  return args_dict   

def loadImageBlobFromFile(imgFile, mean, img_h, img_w):
  import cv2
  img = cv2.imread(imgFile)

  height, width, channels = img.shape
  if height != img_h or width != img_w:
    img = cv2.resize(img, (img_h, img_w))

  # Not needed for Caffe because BGR:
  #img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) # FIXME TF retrained
  mean_arr = np.array(mean)
  array = img - mean_arr

  # prepare blob
  array = np.transpose(array, (2, 0, 1)).flatten()
  #array = array.flatten() # FIXME TF retrained
  return array
  
def loadYoloImageBlobFromFile(imgFile, img_h, img_w):
  # This first loads the image, runs BGR->RGB, converts int 0-255 to floats 0.0-1.0, then letterboxes

  import cv2
  img = cv2.imread(imgFile)

  # YOLO was trained with RGB, not BGR like Caffe:
  img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

  height, width, channels = img.shape
  
  newdim = max(height, width)
  scalew = float(width)/newdim
  scaleh = float(height)/newdim
  neww = int(img_w*scalew)
  newh = int(img_h*scaleh)

  reduced_img = cv2.resize(img, (neww, newh))

  reduced_img_float = np.zeros((img_w, img_w, channels), np.float)
  reduced_img_float = reduced_img/255.0

  newdim = max(newh, neww)
  diffh = newdim - newh
  diffw = newdim - neww
  letter_image_float = np.zeros((newdim,newdim,channels), np.float)
  letter_image_float[:,:,:] = 0.5
  letter_image_float[diffh/2:newh+diffh/2,diffw/2:neww+diffw/2] = reduced_img_float

  # prepare blob (channel, row, column)
  array = np.transpose(letter_image_float, (2, 0, 1)).flatten()

  return array, img.shape

def loadImages (files, transform, img_mean, img_shape):  
  if not isinstance(img_shape, (list,)):
    img_shape = eval(img_shape)
  inputs = np.zeros((len(files), np.prod(img_shape)), dtype=np.float32)
  shapes = [None]*len(files)
  # use raw image files from user

  for i, fname in enumerate(files):
      if transform == 'resize':
          inputs[i] = loadImageBlobFromFile(fname, img_mean, img_shape[1], img_shape[2])    
          shapes[i] = None
      elif transform == 'yolo':
          inputs[i],shapes[i] = loadYoloImageBlobFromFile(fname, img_shape[1], img_shape[2])    
      else:
        assert 0, "Unrecognized image transform"
  
  return inputs,shapes

def loadRawDataInput (file, num_images, img_shape):
  import os
  if not isinstance(img_shape, (list,)):
    img_shape = eval(img_shape)

  inputs = np.zeros((num_images, np.prod(img_shape)), dtype=np.float32)
  shapes = [None]*num_images
  
# use saved image data from framework
  fname = "%s/input" % file 
  if not os.path.isfile(fname):
    raise Exception('Input file not found')
    
  with open(fname, 'r') as f:
    for i in range(num_images):
        line = f.readline()
        if not line:
          break
    
        vals = line.strip().split(' ')
        vals = [float(v) for v in vals]
    
        inputs[i] = vals
        shapes[i] = img_shape
    return inputs,shapes

def printClassification(output, args):
  if isinstance (output, np.ndarray):
    output = output.flatten().tolist()

  labels = []
  with open(args['labels'], 'r') as f:
    for line in f:
      labels.append(line.strip())

  idxArr = []
  for i in range(args['outsz']):
    idxArr.append(i)

  batch_sz = len(output) / args['outsz']
  
  print "\n"
  for i in range(batch_sz):
    inputImage = ""
    if args['images']:
        inputImage = "for %s " % args['images'][i]

    print "---------- Prediction %d %s----------" % (i, inputImage)
    startIdx = i * args['outsz']

    vals = output[startIdx:startIdx + args['outsz']]
    top5 = sorted(zip(vals, idxArr), reverse=True)[:5]

    for j in range(len(top5)):
      print "%.4f - \"%s\"" % (top5[j][0], labels[top5[j][1]])
    print ""  

def XDLFprepareRawInputs( args,RawInputs,batchSize,inH,inW,inChans, PE = -1):
  fpgaInputs = xdnn.prepareInputsForFpga( RawInputs, args['quantizecfg'], args['scaleB'], PE, args['firstfpgalayer'])
  return fpgaInputs
   
def prepareRawInputs( args, PE = -1):
  if args['batch_sz']!=1:
    batch_sz=int(args['batch_sz'])
  else:
    batch_sz = 1
  inputs,shapes = loadRawDataInput ( args['datadir'], batch_sz, args['in_shape'] )
  fpgaInputs = xdnn.prepareInputsForFpga( inputs, args['quantizecfg'], args['scaleB'], PE, args['firstfpgalayer'])
    
  return fpgaInputs, shapes, batch_sz

def prepareImages(args, PE = -1):
  batch_sz = len(args['images'])
  inputs,shapes = loadImages( args['images'], args['transform'], args['img_mean'], args['in_shape'])
  fpgaInputs = xdnn.prepareInputsForFpga( inputs, args['quantizecfg'], args['scaleB'], PE, args['firstfpgalayer'])

  return fpgaInputs, shapes, batch_sz

def loadWeights ( args ) :
  weightsBlob = loadWeightsBiasQuant( args )
  (fcWeight, fcBias) = loadFCWeightsBias(args['datadir'])
  return (weightsBlob, fcWeight, fcBias)

def prepareInput ( args, PE = -1):
  if args['images'] is not None:
    (fpgaInputs, shapes, batch_sz) = prepareImages( args, PE)
  else:
    (fpgaInputs, shapes, batch_sz) = prepareRawInputs( args, PE)
    
  if args['transform'] == 'yolo':
    return fpgaInputs, shapes, batch_sz
  else:
    return fpgaInputs, batch_sz

def prepareOutput(output_sz, batch_sz):
  (fpgaOutput, fpgaHandle) = xdnn.makeFPGAFloatArray(output_sz*batch_sz)

  return fpgaOutput    

def XDLFloadWeights ( args,Weights,outChans,inChans,kernH,kernW,layerName, isxdnnv3=False) :
  print "Loading weights/bias/quant_params to FPGA..."
  
  if isxdnnv3=="True":
    size = xdnn.v3computeWeightsBiasQuantSize(kernW, kernH, outChans, int(math.ceil(float(inChans)/float(96))), 0, 0, False)
    size=size*2
  else:
    size = xdnn.computeWeightsBiasQuantSize(\
          kernW,kernH,inChans,outChans,True if args['quantizecfg'] else False)

  blob = xdnn.makeWeightsBiasQuantBlob(size)
  bias=[0 for v in range(outChans)]
  if isxdnnv3=="True":
    offset = xdnn.v3fillWeightsBiasQuantBlob(blob, 0, 
          args['quantizecfg'], Weights, args['scaleA'], bias, args['scaleB'],
          kernW,kernH,inChans,outChans,layerName)
  else:
    offset = xdnn.fillWeightsBiasQuantBlob(blob, 0, 
          args['quantizecfg'], Weights, args['scaleA'], bias, args['scaleB'],
          kernW,kernH,inChans,outChans,layerName)
  fps = xdnn.loadBlobToDdr(blob, size, int(args['PE']))

  return (blob, fps)

def loadWeightsBiasQuant(args):
  print "Loading weights/bias/quant_params to FPGA..."
  
  size = 0
  fi = 0
  while True:
    fname = "%s/wbq_size_%d" % (args['datadir'], fi)
    if not os.path.isfile(fname):
      break
    
    with open(fname, 'r') as f:
      data = f.read()
      vals = data.strip().split(' ')
      vals = [int(v) for v in vals]
      if 'v2WeightsFormat' in args and args['v2WeightsFormat']==1:
        size += xdnn.computeWeightsBiasQuantSize(\
          vals[0], vals[1], vals[2], vals[3], True if args['quantizecfg'] else False)
      else:
        size += xdnn.computeWeightsBiasQuantSize(\
          vals[0], vals[0], vals[1], vals[2], True if args['quantizecfg'] else False)

    fi += 1

  #print "ANDBG total A size %d" % size
  blob = xdnn.makeWeightsBiasQuantBlob(size)

  fi = 0
  offset = 0
  while True:
    fname = "%s/fwbqb_%d" % (args['datadir'], fi)
    if 'binaryFormatWeights' in args:
      if args['binaryFormatWeights']==1:
        fname="%s/fwbqbbinary_%d.bin" % (args['datadir'],fi)
    if not os.path.isfile(fname):
      break
    
    layerName = None
    weights = None
    bias = None
    if 'v2WeightsFormat' in args and args['v2WeightsFormat']==1:
      kernWidth=None
      kernHeight=None
    else:
      kern = None
    inChans = None
    outChans = None

    if 'binaryFormatWeights' in args:
      if args['binaryFormatWeights']==1:
        if 'v2WeightsFormat' in args and args['v2WeightsFormat']!=1:
          print "Weights should be given in the v2WeightsFormat, KernSizex and KernSizey. If they are already\
            in v2WeightsFormat, then set the argument v2WeightsFormat to 1"
          sys.exit(1)
        vals=[]
        (layerName, kernWidth, kernHeight, inChans, outChans, vals) = xdnn.readWeightsFile(fname)
        weights = [float(v) for v in vals]
      elif args['binaryFormatWeights']==0:
        with open(fname,'r') as f:
          data=f.read()
          vals=data.strip().split(' ')
          layerName = vals[0]
          if 'v2WeightsFormat' in args and args['v2WeightsFormat']==1:
            kernWidth=int(vals[1])
            kernHeight=int(vals[2])
            inChans=int(vals[3])
            outChans=int(vals[4])
            vals=vals[5:]
          else:
            kern = int(vals[1])
            inChans = int(vals[2])
            outChans = int(vals[3])
            vals = vals[4:]
          weights = [float(v) for v in vals]
    else:
      with open(fname, 'r') as f:
        data = f.read()
        vals = data.strip().split(' ')
        layerName = vals[0]
        if 'v2WeightsFormat' in args and args['v2WeightsFormat']==1:
          kernWidth=int(vals[1])
          kernHeight=int(vals[2])
          inChans=int(vals[3])
          outChans=int(vals[4])
          vals=vals[5:]
        else:
          kern = int(vals[1])
          inChans = int(vals[2])
          outChans = int(vals[3])
          vals = vals[4:]
        weights = [float(v) for v in vals]

    fname = "%s/fwbqb_bias_%d" % (args['datadir'], fi)
    with open(fname, 'r') as f:
      data = f.read()
      vals = data.strip().split(' ')
      if 'v2WeightsFormat' in args:
        if args['v2WeightsFormat']==1:
          vals=vals[5:]
        elif args['v2WeightsFormat']==0:
          vals=vals[4:]
      else:
        vals = vals[4:]
      bias = [float(v) for v in vals]

    #print "ANDBG %d %s %d %d %d" % (offset, layerName, fi, len(weights), len(bias))
    if 'v2WeightsFormat' in args and args['v2WeightsFormat']==1:
      offset += xdnn.fillWeightsBiasQuantBlob(blob, offset,
        args['quantizecfg'], weights, args['scaleA'], bias, args['scaleB'],
        kernWidth, kernHeight, inChans, outChans, layerName)
    else:
      offset += xdnn.fillWeightsBiasQuantBlob(blob, offset, 
        args['quantizecfg'], weights, args['scaleA'], bias, args['scaleB'],
        kern, kern, inChans, outChans, layerName)

    fi += 1
  xdnn.loadBlobToDdr(blob, size, int(args['PE']))

  return blob

def getNearFileMatchWithPrefix(path, prefix):
  nearMatches = [f for f in os.listdir(path) if f.startswith(prefix)]
  nearMatches.sort()
  if len(nearMatches) > 0:
    return "%s/%s" % (path, nearMatches[0])

  return None

def loadFCWeightsBias(data_dir):
  weight = []
  fname = "%s/fc" % data_dir
  if not os.path.exists(fname):
    nearMatch = getNearFileMatchWithPrefix(data_dir, "fc")
    if nearMatch:
      fname = nearMatch
  if os.path.exists(fname):
    with open(fname, 'r') as f:
      line = f.read()
      vals = line.strip().split(' ')
      weight = [float(v) for v in vals]
  else:
    print("No FC layers found in %s"% data_dir)
    return (None,None)

  bias = []
  fname = "%s/fc_bias" % data_dir
  if not os.path.exists(fname):
    nearMatch = getNearFileMatchWithPrefix(data_dir, "fc_bias")
    if nearMatch:
      fname = nearMatch
  with open(fname, 'r') as f:
    line = f.read()
    vals = line.strip().split(' ')
    bias = [float(v) for v in vals]

  (weightFpga, fpgaHandle) = xdnn.makeFPGAFloatArray(len(weight))
  (biasFpga, fpgaHandle) = xdnn.makeFPGAFloatArray(len(bias))

  weightFpga[:] = weight
  biasFpga[:] = bias

  return (weightFpga, biasFpga)
