import tensorflow as tf
from modules.modelManagers import FewShotImgLearner


way = 20
t_way = 5
shot = 5
t_shot = 5
backbone = "conv-4-64"


config = {
    "Tensorflow_constants": {
        "seed": 7,
    },

    "Dataset_parameters": {
        "data_dir": r"D:\Datasets\mini-imagenet"
    },

    "model_type": FewShotImgLearner,
    "Model_parameters": {
        "name": f"prototypical_few_shot-{backbone}_"
                f"{way}way{shot}shot_{t_way}tway{t_shot}tshot",
        "method": FewShotImgLearner.Method.PrototypicalNet,
        "sl_kwargs": None,

    },

    "Network_callback_parameters": {
        "verbose": False,
        "save_freq": 1,
        "early_stopping": True,
        "patience": 50,
        "learning_rate_decay_enabled": True,
        "learning_rate_decay_factor": 0.85,
        "learning_rate_decay_freq": 20,
    },

    "Batch_Trainer_parameters": None,

    "FewShot_Trainer_parameters": {
        "n_way": way,
        "n_test_way": t_way,
        "n_shot": shot,
        "n_test_shot": t_shot,
        "n_query": 15,
        "n_test_query": 5,
        "n_train_episodes": 100,
        "n_val_episodes": 100,
        "n_epochs": 300,
        "n_test": 2_000,

        # optimizer
        "learning_rate": 1e-3,
        "optimizer_args": {},
        "optimizer": tf.keras.optimizers.Adam,
        # "optimizer_args": {
        #     "momentum": 0.9,
        #     "decay": 5e-4,
        #     "nesterov": True,
        # },
        # "optimizer": tf.keras.optimizers.SGD,
    }
}
