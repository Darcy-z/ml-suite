#!/bin/bash

for BITWIDTH in 16 8; do
    for DSP_WIDTH in 28; do
        python test_classify.py \
            --xclbin $XCLBIN_PATH/xdnn_v2_32x${DSP_WIDTH}_$((112 / ${DSP_WIDTH}))pe_${BITWIDTH}b_$((2 + ${DSP_WIDTH} / 14))mb_bank21.xclbin \
            --netcfg $MLSUITE_ROOT/examples/compile/work/caffe/vgg16/fp32/vgg16_deploy_${DSP_WIDTH}.cmds \
            --fpgaoutsz 1024 \
            --datadir $MLSUITE_ROOT/examples/compile/work/caffe/vgg16/fp32/vgg16.caffemodel_data \
            --labels synset_words.txt \
            --xlnxlib $LIBXDNN_PATH \
            --images dog.jpg \
            --useblas \
            --quantizecfg $MLSUITE_ROOT/examples/quantize/work/caffe/vgg16/vgg16_quantized_int${BITWIDTH}_deploy.json \
            --firstfpgalayer conv1_1
    done
done

