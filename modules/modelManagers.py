import os

import numpy as np
import tensorflow as tf
from tensorflow.keras.layers import Flatten, Dense, BatchNormalization, Softmax, ReLU, Input
from tensorflow.keras.models import Sequential
from tensorflow.keras.optimizers import SGD
from tensorflow.keras.losses import binary_crossentropy

import modules.util as util
from modules.models import Prototypical
import modules.backbones as backbones
from modules.hyperparameters import *

os.environ["PATH"] += os.pathsep + r'C:\Program Files (x86)\Graphviz2.38\bin/'


class NetworkModelManager:
    available_backbones = {
        "InceptionResNetV2": tf.keras.applications.InceptionResNetV2,
        "InceptionV3": tf.keras.applications.InceptionV3,
        "MobileNet": tf.keras.applications.MobileNet,
        "MobileNetV2": tf.keras.applications.MobileNetV2,
        "ResNet101": tf.keras.applications.ResNet101,
        "ResNet101V2": tf.keras.applications.ResNet101V2,
        "ResNet152": tf.keras.applications.ResNet152,
        "ResNet152V2": tf.keras.applications.ResNet152V2,
        "ResNet50": tf.keras.applications.ResNet50,
        "ResNet50V2": tf.keras.applications.ResNet50V2,
        "VGG16": tf.keras.applications.VGG16,
        "VGG19": tf.keras.applications.VGG19,
        "conv-4-64": backbones.conv_4_64,
    }

    def __init__(self, **kwargs):
        self.name = kwargs.get("name", "network_model")
        os.makedirs("training_data/" + self.name, exist_ok=True)
        self.checkpoint_path = "training_data/" + self.name + "/cp-weights.h5"
        self.history_path = f"training_data/{self.name}/cp-history.json"
        self.checkpoint_dir = os.path.dirname(self.checkpoint_path)
        self.history = dict()
        self.model = None
        self.current_epoch = 0

        self.output_form: util.OutputForm = kwargs.get("output_form", util.OutputForm.LABEL)

        # setting the optimizer
        self.learning_rate = kwargs.get("learning_rate", 1e-3)
        self.momentum = kwargs.get("momentum", CLS_MOMENTUM)
        self.use_nesterov = kwargs.get("use_nesterov", CLS_USE_NESTEROV)
        self.optimizer_args = kwargs.get("optimizer_args", {
            "momentum": self.momentum,
            "nesterov": CLS_USE_NESTEROV,
        })
        self.optimizer = kwargs.get("optimizer", SGD)(self.learning_rate, **self.optimizer_args)

        # metrics
        self.metrics: dict = {"loss": None}

    def summary(self):
        return self.model.summary()

    def load_weights(self):
        assert self.model is not None
        self.model.load_weights(self.checkpoint_path)

    def save_weights(self):
        self.model.save_weights(self.checkpoint_path)

    def load_history(self):
        import json
        if os.path.exists(self.history_path):
            self.history = json.load(open(self.history_path, 'r'))
        self.update_curr_epoch()

    def save_history(self):
        import json

        json.dump(self.history, open(self.history_path, 'w'))

    def update_curr_epoch(self):
        self.current_epoch = len(self.history.get("train", {}).get("loss", []))

    @staticmethod
    def concat_phase_logs(logs_0: dict, logs_1: dict):
        re_logs = {**logs_0, **logs_1}

        for key, value in re_logs.items():
            if key in logs_0 and key in logs_1:
                if hasattr(logs_0[key], '__iter__') and hasattr(value, '__iter__'):
                    re_logs[key] = list(np.array(list(logs_0[key]) + list(value), dtype=float))
                elif not hasattr(logs_0[key], '__iter__') and hasattr(value, '__iter__'):
                    re_logs[key] = list(np.array([logs_0[key]] + list(value), dtype=float))
                elif hasattr(logs_0[key], '__iter__') and not hasattr(value, '__iter__'):
                    re_logs[key] = list(np.array(list(logs_0[key]) + [value], dtype=float))
                else:
                    re_logs[key] = list(np.array([logs_0[key], value], dtype=float))

            else:
                if hasattr(value, '__iter__'):
                    re_logs[key] = list(np.array(list(value), dtype=float))
                else:
                    re_logs[key] = list(np.array([value], dtype=float))

        return re_logs

    def update_history(self, other: dict):
        for _phase, p_logs in other.items():
            self.history[_phase] = self.concat_phase_logs(self.history.get(_phase, {}), p_logs)
        self.save_history()

    def load(self):
        self.load_weights()
        self.load_history()

    def save(self):
        self.save_weights()
        self.save_history()

    def build(self):
        raise NotImplementedError

    def compile(self):
        assert self.model is not None
        self.model.compile(
            optimizer=self.optimizer,
            loss=self.loss_function,
            metrics=[
                tf.keras.metrics.Accuracy(),
            ]
        )
        return self.model

    def build_and_compile(self):
        self.model = self.build()
        self.model = self.compile()

        if len(os.listdir(self.checkpoint_dir)) == 0:
            self.save_weights()
        return self.model

    @staticmethod
    def loss_function(y_true, y_pred, **kwargs):
        raise NotImplementedError()

    def compute_metrics(self, *args, **kwargs) -> dict:
        pass


class NetworkManagerCallback(tf.keras.callbacks.Callback):
    def __init__(self, network_manager: NetworkModelManager, **kwargs):
        super().__init__()

        # base parameters
        self.network_manager = network_manager
        self.verbose = kwargs.get("verbose", True)
        self.save_freq = kwargs.get("save_freq", 1)

        # EarlyStopping parameters
        self.early_stopping_enabled = kwargs.get("early_stopping", True)
        self.early_stopping_patience = kwargs.get("patience", 100)
        self.early_stopping_triggered = False
        self.val_losses = self.network_manager.history.get("val", {}).get("loss", [])

        # Learning rate decay
        self.learning_rate_decay_enabled = kwargs.get("learning_rate_decay_enabled", True)
        self.learning_rate_decay_factor = kwargs.get("learning_rate_decay_factor", 0.5)
        self.learning_rate_decay_freq = kwargs.get("learning_rate_decay_freq", 10)
        self.init_lr = self.network_manager.model.optimizer.learning_rate

    def on_epoch_end(self, epoch, logs=None):
        self.network_manager.current_epoch = epoch

        self._saving_weights(epoch, logs)
        self._early_stopping_func(epoch, logs)
        self._learning_rate_decay_func(epoch, logs)

        self.network_manager.update_history(logs)

    def _saving_weights(self, epoch, logs=None):
        if epoch % self.save_freq == 0:
            if self.verbose:
                print(f"\n Epoch {epoch}: saving model to {self.network_manager.checkpoint_path} \n")
            self.network_manager.save_weights()

    def _early_stopping_func(self, epoch, logs=None):
        if self.early_stopping_enabled:
            self.val_losses.append(logs.get("val", {}).get("loss"))
            if len(self.val_losses) > self.early_stopping_patience \
                    and max(self.val_losses[-self.early_stopping_patience:]) == self.val_losses[-1]:
                self.early_stopping_triggered = True

    def _learning_rate_decay_func(self, epoch, logs=None):
        if self.learning_rate_decay_enabled:
            if epoch % self.learning_rate_decay_freq == 0:
                running_lr = self.init_lr * (self.learning_rate_decay_factor**int(epoch/self.learning_rate_decay_freq))
                self.network_manager.model.optimizer.learning_rate = running_lr


class SelfLearnerWithImgRotation(NetworkModelManager):
    default_backbone = "conv-4-64"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.img_size = kwargs.get("image_size", 80)
        self.output_size = kwargs.get("output_size", 1)
        self.output_form = util.OutputForm.ROT

        self._backbone = kwargs.get("backbone", SelfLearnerWithImgRotation.default_backbone)
        assert self._backbone in NetworkModelManager.available_backbones
        self._backbone_args = kwargs.get(
            "backbone_args",
            {
                "include_top": False,
                "weights": None,
                "input_shape": (self.img_size, self.img_size, 3)
            }
        )
        self._backbone_kwargs = kwargs.get("backbone_kwargs", {})

        self._nb_hidden_layer: int = kwargs.get("nb_hidden_layers", 1)
        self._hidden_neurons: list = kwargs.get("hidden_neurons", [4096 for _ in range(self._nb_hidden_layer)])

        assert self._nb_hidden_layer == len(self._hidden_neurons)

        self.classifier = Sequential(
            Flatten(),
            ReLU(),
            *[
                Sequential([
                    Dense(h),
                    BatchNormalization(),
                    ReLU(),
                ], name="Dense_Block")
                for h in self._hidden_neurons
            ],
            Dense(self.output_size, name="output_layer"),
            Softmax(),
        )

    def build(self):
        self.model = Sequential(
            [
                self.available_backbones.get(self._backbone)(
                    **self._backbone_args, **self._backbone_kwargs
                ),
                self.classifier,
            ]
        )

        return self.model

    @staticmethod
    def loss_function(y_true, y_pred, **kwargs):
        return tf.keras.losses.binary_crossentropy(y_true, y_pred, from_logits=kwargs.get("from_logits", False))


class FewShotImgLearner(NetworkModelManager):
    default_backbone = "conv-4-64"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.img_size = kwargs.get("image_size", 84)
        self.channels = kwargs.get("channels", 3)

        self._backbone = kwargs.get("backbone", FewShotImgLearner.default_backbone)
        assert self._backbone in NetworkModelManager.available_backbones
        self._backbone_args = kwargs.get(
            "backbone_args",
            {
                "include_top": False,
                "weights": None,
                "input_shape": (self.img_size, self.img_size, self.channels)
            }
        )
        self._backbone_kwargs = kwargs.get("backbone_kwargs", {})

    def build(self):
        self.model = Prototypical(
            # n_query=,
            # n_support=,
            w=self.img_size,
            h=self.img_size,
            c=self.channels,
            backbone=self.available_backbones.get(self._backbone)(**self._backbone_args, **self._backbone_kwargs)
        )

        return self.model

    @staticmethod
    def loss_function(y_true, y_pred, **kwargs):
        return tf.keras.losses.binary_crossentropy(y_true, y_pred, from_logits=kwargs.get("from_logits", False))


class BoostedFewShotLearner(NetworkModelManager):
    default_backbone = "conv-4-64"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.img_size = kwargs.get("image_size", 84)
        self.channels = kwargs.get("channels", 3)
        self.input_shape = (self.img_size, self.img_size, self.channels)

        self._backbone = kwargs.get("backbone", FewShotImgLearner.default_backbone)
        assert self._backbone in NetworkModelManager.available_backbones
        self._backbone_args = kwargs.get(
            "backbone_args",
            {
                "include_top": False,
                "weights": None,
                "input_shape": self.input_shape
            }
        )
        self._backbone_kwargs = kwargs.get("backbone_kwargs", {})

        # SL stuff
        self.sl_output_size = kwargs.get("sl_output_size", 1)
        self._nb_hidden_layer: int = kwargs.get("nb_hidden_layers", 1)
        self._hidden_neurons: list = kwargs.get("hidden_neurons", [4096 for _ in range(self._nb_hidden_layer)])

        assert self._nb_hidden_layer == len(self._hidden_neurons)

        self.sl_classifier_layers = [
            Flatten(),
            ReLU(),
            *[
                Sequential([
                    Dense(h),
                    BatchNormalization(),
                    ReLU(),
                ], name="Dense_Block")
                for h in self._hidden_neurons
            ],
            Dense(self.sl_output_size, name="sl_output_layer"),
            Softmax(),
        ]

    def build(self):
        _backbone = self.available_backbones.get(self._backbone)(**self._backbone_args, **self._backbone_kwargs)
        print(f"_backbone.output_shape: {_backbone.output_shape}")
        _cls_input = Input(shape=_backbone.output_shape)
        _seq = Sequential(self.sl_classifier_layers)
        print(f"_seq: {_seq}")
        _cls = tf.keras.Model(_cls_input, _seq(_cls_input))
        print(f"_cls: {_cls}")
        self.model = Prototypical(
            w=self.img_size,
            h=self.img_size,
            c=self.channels,
            backbone=_backbone,
            sl_classifier=_cls,
        )

        self.model.build()

        return self.model

    @staticmethod
    def loss_function(y_true, y_pred, **kwargs):
        return tf.keras.losses.binary_crossentropy(y_true, y_pred, from_logits=kwargs.get("from_logits", False))


if __name__ == '__main__':
    self_learner = SelfLearnerWithImgRotation()
    self_learner.build_and_compile()
    self_learner.summary()

    self_learner.update_history({"loss": [0.16546546874, ], "accuracy": np.array([0.156496848, ])})
    self_learner.save_history()
    self_learner.load_history()
    print(self_learner.history)