import os
import math
import yaml
import torch

os.environ["TOKENIZERS_PARALLELISM"] = "false"

# =====================================
# Import Training Parameters
# =====================================

params = yaml.safe_load(open("params.yaml"))

# =====================================
# Import Training Data
# =====================================

# huggingface's datasets library
from datasets import load_dataset

# import the ConLL2003 dataset
dataset = load_dataset("conll2003")

# get and generate the label mappings
labels = dataset["train"].features["ner_tags"].feature
label2id = {k: labels.str2int(k) for k in labels.names}

# =====================================
# Define the Model
# =====================================

from library.NERModel import NERModel

# get the model name
model_name = params["model_name"]
# get the training parameters
training = params["training"]
lr = training["learning_rate"]
wd = training["weight_decay"]
eps = training["epsilon"]

# initialize the model
model = NERModel(model_name, label2id=label2id, lr=lr, wd=wd, eps=eps)

# =====================================
# Prepare the Training Data
# =====================================


def add_encodings(example):
    """Processing the example

    Args:
        example (dict): The dataset example.

    Returns:
        dict: The dictionary containing the following updates:
            - input_ids: The list of input ids of the tokens.
            - attention_mask: The attention mask list.
            - ner_tags: The updated ner_tags.

    """
    # get the encodings of the tokens. The tokens are already split, that is why we must add is_split_into_words=True
    encodings = model.tokenizer(
        example["tokens"],
        truncation=True,
        padding="max_length",
        is_split_into_words=True,
    )
    # extend the ner_tags so that it matches the max_length of the input_ids
    labels = example["ner_tags"] + [0] * (
        model.tokenizer.model_max_length - len(example["ner_tags"])
    )
    # return the encodings and the extended ner_tags
    return {**encodings, "labels": labels}


# modify/format all datasets so that they include the "input_ids", "attention_mask"
# and "labels" used to train and evaluate the model
dataset = dataset.map(add_encodings)

# format the datasets so that we return only "input_ids", "attention_mask" and "labels"
# making it easier to train and validate the model
dataset.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])

# ===========================
# get parameters
# ===========================

epochs = training["epochs"]
grad_step = training["grad_step"]
batch_size = training["batch_size"]

# use a third of the workers for each data loader
num_workers = math.floor(os.cpu_count() / 3)

# prepare the train and validation data
data_train = torch.utils.data.DataLoader(
    dataset["train"], batch_size=batch_size, num_workers=num_workers, pin_memory=True,
)
data_val = torch.utils.data.DataLoader(
    dataset["validation"],
    batch_size=batch_size,
    num_workers=num_workers,
    pin_memory=True,
)

# =====================================
# Execute the Training Process
# =====================================


import pytorch_lightning as pl
from pytorch_lightning.loggers import TestTubeLogger
from pytorch_lightning.callbacks import ModelCheckpoint

# initialize the logger
tb_logger = TestTubeLogger(save_dir="logs/", name=model_name,)

# create a checkpoint callback
checkpoint_callback = ModelCheckpoint(
    monitor="val_loss",
    filename=model_name + "_epoch{epoch:02d}_{val_loss:.2f}",
    auto_insert_metric_name=False,
    save_top_k=3,
    mode="min",
)

# initialize the trainer
trainer = pl.Trainer(
    gpus=1,  # run on one gpu
    logger=tb_logger,  # format logs for tensorboard
    max_epochs=epochs,  # maximum number of epochs
    accumulate_grad_batches=grad_step,  # when to trigger optimizer step
    callbacks=[checkpoint_callback],
)
# start the training process
trainer.fit(model, data_train, data_val)
