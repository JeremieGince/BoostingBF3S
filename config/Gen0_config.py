import tensorflow as tf
from modules.modelManagers import FewShotImgLearner
from modules import util
from modules.trainers import TrainerType


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
        "name": f"Gen0-{backbone}"
                f"_{t_way}tway{t_shot}tshot"
                f"_97",
        "method": FewShotImgLearner.Method.Gen0,
        "alpha": 1.0,
        "sl_kwargs": None,
        "n_cls_base": 64,
        "n_cls_val": 16,
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

    "Trainers_parameters": [
        {
            "trainer_type": TrainerType.MixedTrainer,
            "gen_trainer_type": {
                util.TrainingPhase.TRAIN: TrainerType.BatchTrainer,
                util.TrainingPhase.VAL: TrainerType.EpisodicTrainer,
                util.TrainingPhase.TEST: TrainerType.EpisodicTrainer,
            },
            "n_train_batch": 100,
            "n_val_batch": 0,

            "n_way": way,
            "n_test_way": t_way,
            "n_shot": shot,
            "n_test_shot": t_shot,
            "n_query": 15,
            "n_test_query": 5,
            "n_train_episodes": 0,
            "n_val_episodes": 100,

            "n_epochs": 97,
            "n_test": 2_000,

            # optimizer
            "learning_rate": 1e-3,
            "optimizer_args": {},
            "optimizer": tf.keras.optimizers.Adam,
        }
    ]
}
