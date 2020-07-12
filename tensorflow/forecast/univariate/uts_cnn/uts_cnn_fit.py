import argparse
import csv
import time
import os
import numpy as np
import tensorflow as tf
import tensorflow.keras.optimizers as tko
import tensorflow.keras.activations as tka
import tensorflow.keras.losses as tkl
import tensorflow.keras.metrics as tkm
import tensorflow.keras.callbacks as tfcb
import tensorflow.keras.initializers as tfi
from tensorflow.keras.layers import Input, Dense, Conv1D, MaxPooling1D, Dropout, Flatten, concatenate
from tensorflow.keras.models import Model
import pandas as pd

def str2bool(v):
    if isinstance(v, bool):
       return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def build_samples(seq):
    df = pd.DataFrame(seq)
    cols = list()
    for i in range(args.sample_length, 0, -1):
        cols.append(df.shift(i))

    for i in range(0, 1):
        cols.append(df.shift(-i))

    aggregate = pd.concat(cols, axis=1)
    aggregate.dropna(inplace=True)

    X_train, y_train = aggregate.values[:, :-1], aggregate.values[:, -1]
    X_train = X_train.reshape((X_train.shape[0], X_train.shape[1], 1))
    return X_train, y_train

def build_cnn_layer(cnn_layer_layout):
    if cnn_layer_layout.startswith('conv'):
        tupla_par = '(' + cnn_layer_layout.split('(', 1)[1]
        tupla_par = eval(tupla_par)
        if len(tupla_par) == 5:
            filters, kernel_size, activation, kinit, binit = tupla_par
            kinit = build_initializer(kinit)
            binit = build_initializer(binit)
        elif len(tupla_par) == 4:
            filters, kernel_size, activation, kinit = tupla_par
            kinit = build_initializer(kinit)
            binit = 'zeros'
        else:
            filters, kernel_size, activation = tupla_par
            kinit, binit ='glorot_uniform', 'zeros'
        cnn_layer = Conv1D(
            filters=filters,
            kernel_size=kernel_size,
            activation=activation,
            kernel_initializer=kinit,
            bias_initializer=binit)
    elif cnn_layer_layout.startswith('maxpool'):
        tupla_par = '(' + cnn_layer_layout.split('(', 1)[1]
        tupla_par = eval(tupla_par)
        pool_size = tupla_par
        cnn_layer = MaxPooling1D(pool_size=pool_size)
    elif cnn_layer_layout.startswith('dropout'):
        tupla_par = '(' + cnn_layer_layout.split('(', 1)[1]
        tupla_par = eval(tupla_par)
        rate = tupla_par
        cnn_layer = Dropout(rate=rate)
    else:
        raise Exception('Unsupported cnn layer layout \'%s\'' % cnn_layer)

    return cnn_layer

def build_model():
    inputs = Input(shape=(args.sample_length, 1))

    cnn = inputs
    for i in range(0, len(args.cnn_layers_layout)):
        cnn = build_cnn_layer(args.cnn_layers_layout[i])(cnn)

    #cnn = Conv1D(64, 3, activation='relu')(inputs)
    #cnn = MaxPooling1D()(cnn)
    #cnn = Conv1D(64, 1, activation='tanh')(cnn)
    #cnn = Conv1D(64, 1, activation='relu')(cnn)
    #cnn = MaxPooling1D()(cnn)

    hidden = Flatten()(cnn)

    for i in range(0, len(args.dense_layers_layout)):
        kernel_initializer = build_initializer(args.dense_weight_initializers[i]) if i < len(args.dense_weight_initializers) else None
        bias_initializer = build_initializer(args.dense_bias_initializers[i]) if i < len(args.dense_bias_initializers) else None
        hidden = Dense(
            args.dense_hidden_layers_layout[i],
            use_bias = True,
            activation = build_activation_function(args.dense_activation_functions[i]),
            kernel_initializer = kernel_initializer,
            bias_initializer = bias_initializer
            )(hidden)

    outputs = Dense(1)(hidden)
    model = Model(inputs=inputs, outputs=outputs)
    return model

def build_initializer(init):
    exp_init = 'lambda _ : tfi.' + init
    return eval(exp_init)(None)

def build_activation_function(af):
    if af.lower() == 'none':
        return None
    exp_af = 'lambda _ : tka.' + af
    return eval(exp_af)(None)

def build_optimizer():
    opt_init = args.optimizer
    exp_po = 'lambda _ : tko.' + opt_init
    optimizer = eval(exp_po)(None)
    return optimizer

def build_loss():
    exp_loss = 'lambda _ : tkl.' + args.loss
    return eval(exp_loss)(None)

def read_timeseries(tsfilename):
    y_values = []
    with open(tsfilename) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        next(csv_reader, None)
        for row in csv_reader:
            y_values.append(float(row[0]))
    return y_values

class EpochLogger(tfcb.Callback):
    def on_epoch_end(self, epoch, logs=None):
        if  (epoch % args.model_snapshots_freq == 0) or ((epoch + 1) == args.epochs):
            self.model.save(os.path.join(args.model_snapshots_path, format(epoch, '09')))
            print ('\nSaved #{} snapshot model'.format(epoch, '09'))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='%(prog)s builds a model to fit an univariate time series using a configurable CNN neural network')

    parser.add_argument('--version', action='version', version='%(prog)s 1.0.0')

    parser.add_argument('--tstrain',
                        type=str,
                        dest='train_timeseries_filename',
                        required=True,
                        help='univariate time series file (csv format) for training')

    parser.add_argument('--modelout',
                        type=str,
                        dest='model_path',
                        required=True,
                        help='output model directory')

    parser.add_argument('--samplelength',
                        type=int,
                        dest='sample_length',
                        required=False,
                        default=5,
                        help='sample length')

    parser.add_argument('--bestmodelmonitor',
                        type=str,
                        dest='best_model_monitor',
                        required=False,
                        help='quantity to monitor in order to save the best model')

    parser.add_argument('--epochs',
                        type=int,
                        dest='epochs',
                        required=False,
                        default=500,
                        help='number of epochs')

    parser.add_argument('--batchsize',
                        type=int,
                        dest='batch_size',
                        required=False,
                        default=50,
                        help='batch size')

    parser.add_argument('--cnnlayers',
                        type=str,
                        nargs = '+',
                        dest='cnn_layers_layout',
                        required=True,
                        help='cnn hidden layers')

    parser.add_argument('--denselayers',
                        type=int,
                        nargs = '+',
                        dest='dense_layers_layout',
                        required=False,
                        default=[],
                        help='number of neurons for each dense layers')

    parser.add_argument('--denseactivations',
                        type=str,
                        nargs = '+',
                        dest='dense_activation_functions',
                        required=False,
                        default=[],
                        help='activation functions between dense layers')

    parser.add_argument('--densewinitializers',
                        type=str,
                        nargs = '+',
                        dest='dense_weight_initializers',
                        required=False,
                        default=[],
                        help='list of initializers (one for each dense layer) of the dense weights')

    parser.add_argument('--densebinitializers',
                        type=str,
                        nargs = '+',
                        dest='dense_bias_initializers',
                        required=False,
                        default=[],
                        help='list of initializers (one for each dense layer) of the dense bias')

    parser.add_argument('--optimizer',
                        type=str,
                        dest='optimizer',
                        required=False,
                        default='Adam()',
                        help='optimizer algorithm')

    parser.add_argument('--loss',
                        type=str,
                        dest='loss',
                        required=False,
                        default='MeanSquaredError()',
                        help='loss function name')

    parser.add_argument('--metrics',
                        type=str,
                        nargs = '+',
                        dest='metrics',
                        required=False,
                        default=[],
                        help='list of metrics to compute')

    parser.add_argument('--dumpout',
                        type=str,
                        dest='dumpout_path',
                        required=False,
                        help='dump directory (directory to store loss and metric values)')

    parser.add_argument('--logsout',
                        type=str,
                        dest='logsout_path',
                        required=False,
                        help='logs directory for TensorBoard')

    parser.add_argument('--modelsnapout',
                        type=str,
                        dest='model_snapshots_path',
                        required=False,
                        help='output model snapshots directory')

    parser.add_argument('--modelsnapfreq',
                        type=int,
                        dest='model_snapshots_freq',
                        required=False,
                        default=25,
                        help='frequency in epochs to make the snapshot of model')

    args = parser.parse_args()

    if len(args.dense_layers_layout) != len(args.dense_activation_functions):
        raise Exception('Number of dense hidden layers and number of dense activation functions must be equals')

    print("#### Started %s ####" % os.path.basename(__file__));

    sequence = read_timeseries(args.train_timeseries_filename)
    X_train, y_train = build_samples(sequence)

    model = build_model()

    optimizer = build_optimizer()
    loss=build_loss()
    model.compile(loss=loss, optimizer=optimizer, metrics = args.metrics)
    model.summary()

    tf_callbacks = []
    if args.logsout_path:
        tf_callbacks.append(tfcb.TensorBoard(log_dir=args.logsout_path, histogram_freq=0, write_graph=True, write_images=True))
    if args.model_snapshots_path:
        tf_callbacks.append(EpochLogger())
    if args.best_model_monitor:
        tf_callbacks.append(tfcb.ModelCheckpoint(
            filepath = args.model_path,
            save_best_only = True,
            monitor = args.best_model_monitor,
            mode = 'auto',
            verbose=1))

    start_time = time.time()
    history = model.fit(
        X_train, y_train,
        epochs=args.epochs,
        batch_size=args.batch_size,
        verbose=1,
        callbacks=tf_callbacks)
    elapsed_time = time.time() - start_time
    print ("Training time:", time.strftime("%H:%M:%S", time.gmtime(elapsed_time)))

    if not args.best_model_monitor:
        model.save(args.model_path)
        print ('\nSaved last recent model')

    if args.dumpout_path is not None:
        if not os.path.exists(args.dumpout_path):
            os.makedirs(args.dumpout_path)
        np.savetxt(os.path.join(args.dumpout_path, 'loss_' + loss.name + '.csv'), history.history['loss'], delimiter=',')
        for metric in args.metrics:
            np.savetxt(os.path.join(args.dumpout_path, 'metric_' + metric + '.csv'), history.history[metric], delimiter=',')

    print("#### Terminated %s ####" % os.path.basename(__file__));