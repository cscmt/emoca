import os, sys
from pathlib import Path
from omegaconf import DictConfig, OmegaConf
from gdl.datasets.AffectNetDataModule import AffectNetDataModule
from gdl_apps.DECA.train_expdeca import prepare_data, create_logger
from gdl_apps.DECA.train_deca_modular import get_checkpoint, locate_checkpoint

from gdl.models.EmoDECA import EmoDECA
from gdl.models.EmoNetModule import EmoNetModule
from gdl.models.EmoSwinModule import EmoSwinModule
from gdl.utils.other import class_from_str
import datetime
from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import ModelCheckpoint, EarlyStopping
from gdl_apps.DECA.interactive_deca_decoder import hack_paths


project_name = 'EmoDECA'


def create_experiment_name(cfg, version=1):
    if cfg.model.emodeca_type == "EmoDECA":
        experiment_name = "EmoDECA"
        if cfg.data.data_class:
            experiment_name += '_' + cfg.data.data_class[:5]

        if cfg.model.deca_cfg.model.resume_training and cfg.model.deca_cfg.inout.name == 'todo':
            experiment_name += "_Orig"
        else:
            # experiment_name += "_" + cfg.model.deca_cfg.inout.name
            experiment_name += "_" + cfg.model.deca_cfg.model.deca_class

        if "use_mlp" not in cfg.model.keys() or cfg.model.use_mlp:
            experiment_name += f"_nl-{cfg.model.num_mlp_layers}"

            if "mlp_norm_layer" in cfg.model.keys() and cfg.model.mlp_norm_layer:
                experiment_name += cfg.model.mlp_norm_layer

            if cfg.model.use_identity:
                experiment_name += "_id"
            if cfg.model.use_expression:
                experiment_name += "_exp"
            if cfg.model.use_global_pose:
                experiment_name += "_pose"
            if cfg.model.use_jaw_pose:
                experiment_name += "_jaw"
            if cfg.model.use_detail_code:
                experiment_name += "_detail"

        if "use_emonet" in cfg.model.keys() and cfg.model.use_emonet:
            experiment_name += "_EmoNet"
            if cfg.model.use_coarse_image_emonet:
                experiment_name += "C"
            if cfg.model.use_detail_image_emonet:
                experiment_name += "D"

            if cfg.model.unpose_global_emonet:
                experiment_name += "_unpose"
            if cfg.model.static_light:
                experiment_name += "_light"
            if cfg.model.static_cam_emonet:
                experiment_name += "_cam"

    elif cfg.model.emodeca_type == "EmoNetModule":
        experiment_name = "EmoNet"
    elif cfg.model.emodeca_type == "EmoSwinModule":
        experiment_name = "EmoSwin"
        experiment_name += "_" + cfg.model.swin_type
    else:
        raise ValueError(f"Invalid emodeca_type: '{cfg.model.emodeca_type}'")

    if 'continuous_va_balancing' in cfg.model.keys():
        experiment_name += "_va" + cfg.model.continuous_va_balancing

    if 'va_loss_scheme' in cfg.model.keys():
        experiment_name += "_" + cfg.model.va_loss_scheme

    if cfg.model.expression_balancing:
        experiment_name += "_balanced"

    if 'augmentation' in cfg.data.keys() and len(cfg.data.augmentation) > 0:
        experiment_name += "_Aug"

    if hasattr(cfg.learning, 'early_stopping') and cfg.learning.early_stopping:
        experiment_name += "_early"

    if cfg.learning.optimizer != 'Adam':
        experiment_name += "_" + cfg.learning.optimizer

    if 'learning_rate_patience' in cfg.learning.keys():
        experiment_name += "_RLROP"

    if 'learning_rate_decay' in cfg.learning.keys():
        experiment_name += f"_d{cfg.learning.learning_rate_decay:0.4f}"


    return experiment_name


def single_stage_deca_pass(deca, cfg, stage, prefix, dm=None, logger=None,
                           data_preparation_function=None,
                           checkpoint=None, checkpoint_kwargs=None):
    if dm is None:
        dm, sequence_name = data_preparation_function(cfg)

    if logger is None:
        N = len(datetime.datetime.now().strftime("%Y_%m_%d_%H-%M-%S"))

        if hasattr(cfg.inout, 'time') and hasattr(cfg.inout, 'random_id'):
            version = cfg.inout.time + "_" + cfg.inout.random_id
        elif hasattr(cfg.inout, 'time'):
            version = cfg.inout.time + "_" + cfg.inout.name
        else:
            version = sequence_name[:N] # unfortunately time doesn't cut it if two jobs happen to start at the same time

        logger = create_logger(
                    cfg.learning.logger_type,
                    name=cfg.inout.name,
                    project_name=project_name,
                    version=version,
                    save_dir=cfg.inout.full_run_dir)

    if deca is None:
        if 'emodeca_type' in cfg.model:
            deca_class = class_from_str(cfg.model.emodeca_type, sys.modules[__name__])
        else:
            deca_class = EmoDECA

        if logger is not None:
            logger.finalize("")
        if checkpoint is None:
            deca = deca_class(cfg)
        else:
            checkpoint_kwargs = checkpoint_kwargs or {}
            deca = deca_class.load_from_checkpoint(checkpoint_path=checkpoint, strict=False, **checkpoint_kwargs)

    deca_class = type(deca)


    # accelerator = None if cfg.learning.num_gpus == 1 else 'ddp2'
    # accelerator = None if cfg.learning.num_gpus == 1 else 'ddp'
    # accelerator = None if cfg.learning.num_gpus == 1 else 'ddp_spawn' # ddp only seems to work for single .fit/test calls unfortunately,
    accelerator = None if cfg.learning.num_gpus == 1 else 'dp'  # ddp only seems to work for single .fit/test calls unfortunately,

    if accelerator is not None and 'LOCAL_RANK' not in os.environ.keys():
        print("SETTING LOCAL_RANK to 0 MANUALLY!!!!")
        os.environ['LOCAL_RANK'] = '0'

    loss_to_monitor = 'val_loss_total'
    dm.setup()
    val_data = dm.val_dataloader()
    if isinstance(val_data, list):
        loss_to_monitor = loss_to_monitor + "/dataloader_idx_0"
        # loss_to_monitor = '0_' + loss_to_monitor + "/dataloader_idx_0"
    # if len(prefix) > 0:
    #     loss_to_monitor = prefix + "_" + loss_to_monitor

    callbacks = []
    checkpoint_callback = ModelCheckpoint(
        monitor=loss_to_monitor,
        filename='deca-{epoch:02d}-{' + loss_to_monitor + ':.8f}',
        save_top_k=3,
        save_last=True,
        mode='min',
        dirpath=cfg.inout.checkpoint_dir
    )
    callbacks += [checkpoint_callback]
    if hasattr(cfg.learning, 'early_stopping') and cfg.learning.early_stopping:
        patience = 3
        if hasattr(cfg.learning.early_stopping, 'patience') and cfg.learning.early_stopping.patience:
            patience = cfg.learning.early_stopping.patience

        early_stopping_callback = EarlyStopping(monitor=loss_to_monitor,
                                                mode='min',
                                                patience=patience,
                                                strict=True)
        callbacks += [early_stopping_callback]


    val_check_interval = 1.0
    if 'val_check_interval' in cfg.learning.keys():
        val_check_interval = cfg.learning.val_check_interval
    print(f"Setting val_check_interval to {val_check_interval}")

    max_steps = None
    if hasattr(cfg.learning, 'max_steps'):
        max_steps = cfg.learning.max_steps
        print(f"Setting max steps to {max_steps}")

    print(f"After training checkpoint strategy: {cfg.learning.checkpoint_after_training}")

    trainer = Trainer(gpus=cfg.learning.num_gpus,
                      max_epochs=cfg.learning.max_epochs,
                      max_steps=max_steps,
                      default_root_dir=cfg.inout.checkpoint_dir,
                      logger=logger,
                      accelerator=accelerator,
                      callbacks=callbacks,
                      val_check_interval=val_check_interval,
                      # num_sanity_val_steps=0
                      )

    if stage == "train":
        # trainer.fit(deca, train_dataloader=train_data_loader, val_dataloaders=[val_data_loader, ])
        trainer.fit(deca, datamodule=dm)
        if hasattr(cfg.learning, 'checkpoint_after_training'):
            if cfg.learning.checkpoint_after_training == 'best':
                print(f"Loading the best checkpoint after training '{checkpoint_callback.best_model_path}'.")
                deca = deca_class.load_from_checkpoint(checkpoint_callback.best_model_path,
                                                       config=cfg,
                                                       )
            elif cfg.learning.checkpoint_after_training == 'latest':
                print(f"Keeping the lastest weights after training.")
                pass # do nothing, the latest is obviously loaded
            else:
                print(f"[WARNING] Unexpected value of cfg.learning.checkpoint_after_training={cfg.learning.checkpoint_after_training}. "
                      f"Will do nothing")

    elif stage == "test":
        # trainer.test(deca,
        #              test_dataloaders=[test_data_loader],
        #              ckpt_path=None)
        trainer.test(deca,
                     datamodule=dm,
                     ckpt_path=None)
    else:
        raise ValueError(f"Invalid stage {stage}")
    if logger is not None:
        logger.finalize("")
    return deca


def get_checkpoint_with_kwargs(cfg, prefix, replace_root = None, relative_to = None, checkpoint_mode=None):
    checkpoint = get_checkpoint(cfg, replace_root = replace_root,
                                relative_to = relative_to, checkpoint_mode=checkpoint_mode)
    cfg.model.resume_training = False  # make sure the training is not magically resumed by the old code
    # checkpoint_kwargs = {
    #     "model_params": cfg.model,
    #     "learning_params": cfg.learning,
    #     "inout_params": cfg.inout,
    #     "stage_name": prefix
    # }
    checkpoint_kwargs = {'config': cfg}
    return checkpoint, checkpoint_kwargs


def train_emodeca(cfg, start_i=0, resume_from_previous = True,
                  force_new_location=False):
    configs = [cfg, cfg]
    # configs = [cfg,]
    stages = ["train", "test"]
    # stages = ["test",]
    stages_prefixes = ["", ""]

    if start_i > 0 or force_new_location:
        if resume_from_previous:
            resume_i = start_i - 1
            checkpoint_mode = None # loads latest or best based on cfg
            print(f"Resuming checkpoint from stage {resume_i} (and will start from the next stage {start_i})")
        else:
            resume_i = start_i
            print(f"Resuming checkpoint from stage {resume_i} (and will start from the same stage {start_i})")
            checkpoint_mode = 'latest' # resuming in the same stage, we want to pick up where we left of
        checkpoint, checkpoint_kwargs = get_checkpoint_with_kwargs(configs[resume_i], stages_prefixes[resume_i], checkpoint_mode)
    else:
        checkpoint, checkpoint_kwargs = None, None

    if cfg.inout.full_run_dir == 'todo' or force_new_location:
        if force_new_location:
            print("The run will be resumed in a new foler (forked)")
        time = datetime.datetime.now().strftime("%Y_%m_%d_%H-%M-%S")
        random_id = str(hash(time))
        experiment_name = create_experiment_name(cfg)
        full_run_dir = Path(configs[0].inout.output_dir) / (time + "_" + experiment_name)
        exist_ok = False # a path for a new experiment should not yet exist
    else:
        experiment_name = cfg.inout.name
        len_time_str = len(datetime.datetime.now().strftime("%Y_%m_%d_%H-%M-%S"))
        if hasattr(cfg.inout, 'time') and cfg.inout.time is not None:
            time = cfg.inout.time
        else:
            time = experiment_name[:len_time_str]
        if hasattr(cfg.inout, 'random_id') and cfg.inout.random_id is not None:
            random_id = cfg.inout.random_id
        else:
            random_id = ""
        full_run_dir = Path(cfg.inout.full_run_dir).parent
        exist_ok = True # a path for an old experiment should exist

    full_run_dir.mkdir(parents=True, exist_ok=exist_ok)
    print(f"The run will be saved  to: '{str(full_run_dir)}'")
    with open("out_folder.txt", "w") as f:
        f.write(str(full_run_dir))

    checkpoint_dir = full_run_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=exist_ok)

    cfg.inout.full_run_dir = str(checkpoint_dir.parent)
    cfg.inout.checkpoint_dir = str(checkpoint_dir)
    cfg.inout.name = experiment_name
    cfg.inout.time = time
    cfg.inout.random_id = random_id

    with open(full_run_dir / "cfg.yaml", 'w') as outfile:
        OmegaConf.save(config=cfg, f=outfile)


    version = time
    if random_id is not None and len(random_id) > 0:
        version += "_" + cfg.inout.random_id

    logger = create_logger(
                         cfg.learning.logger_type,
                         name=experiment_name,
                         project_name=project_name,
                         config=OmegaConf.to_container(cfg),
                         version=version,
                         save_dir=full_run_dir)

    deca = None
    if start_i > 0 or force_new_location:
        print(f"Loading a checkpoint: {checkpoint} and starting from stage {start_i}")

    for i in range(start_i, len(configs)):
        cfg = configs[i]
        deca = single_stage_deca_pass(deca, cfg, stages[i], stages_prefixes[i], dm=None, logger=logger,
                                      data_preparation_function=prepare_data,
                                      checkpoint=checkpoint, checkpoint_kwargs=checkpoint_kwargs)
        checkpoint = None


def configure(emo_deca_default, emodeca_overrides, deca_default, deca_overrides, deca_conf_path=None, deca_stage=None,
              replace_root_path=None, relative_to_path=None):
    from hydra.experimental import compose, initialize
    from hydra.core.global_hydra import GlobalHydra
    initialize(config_path="emodeca_conf", job_name="train_deca")
    cfg = compose(config_name=emo_deca_default, overrides=emodeca_overrides)

    if deca_default is not None or deca_conf_path is not None:
        if deca_conf_path is None:
            GlobalHydra.instance().clear()
            initialize(config_path="../DECA/deca_conf", job_name="train_deca")
            deca_cfg = compose(config_name=deca_default, overrides=deca_overrides)
            cfg.model.deca_checkpoint = None
        else:
            if deca_default is not None:
                raise ValueError("Pass either a path to a deca config or a set of parameters to configure. Not both")
            with open(Path(deca_conf_path) / "cfg.yaml", "r") as f:
                deca_cfg = OmegaConf.load(f)
            deca_cfg = deca_cfg[deca_stage]

            ckpt = locate_checkpoint(deca_cfg, replace_root=replace_root_path, relative_to=relative_to_path, mode='best')
            cfg.model.deca_checkpoint = ckpt
            if replace_root_path is not None and relative_to_path is not None:
                deca_cfg = hack_paths(deca_cfg, replace_root_path=replace_root_path, relative_to_path=relative_to_path)

        cfg.model.deca_cfg = deca_cfg
        cfg.model.deca_stage = deca_stage

    if 'swin_type' in cfg.model.keys():
        if cfg.model.swin_cfg == 'todo':
            swin_cfg = OmegaConf.load(
                Path(__file__).parents[3] / "SwinTransformer" / "configs" / (cfg.model.swin_type + ".yaml"))
            OmegaConf.set_struct(swin_cfg, True)
            cfg.model.swin_cfg = swin_cfg
    return cfg


def load_configs(run_path):
    with open(Path(run_path) / "cfg.yaml", "r") as f:
        conf = OmegaConf.load(f)
    return conf


def resume_training(run_path, start_at_stage, resume_from_previous, force_new_location):
    cfg = load_configs(run_path)
    train_emodeca(cfg, start_i=start_at_stage, resume_from_previous = resume_from_previous,
                  force_new_location=force_new_location)


def main():
    if len(sys.argv) < 2:

        # #1 EMONET
        # emodeca_default = "emonet"
        # emodeca_overrides = [
        #     # 'model/settings=emonet_trainable',
        #     'model/settings=emonet_trainable_weighted_va',
        #     'learning/logging=none',
        #     # 'learning.max_steps=1',
        #     'learning.max_epochs=1',
        #     'learning.checkpoint_after_training=latest',
        #     '+learning/lr_scheduler=reduce_on_plateau',
        #     # 'model.continuous_va_balancing=1d',
        #     # 'model.continuous_va_balancing=2d',
        #     # 'model.continuous_va_balancing=expr',
        #     # 'learning.val_check_interval=1',
        #     # 'learning.learning_rate=0',
        #     # 'learning/optimizer=adabound',
        #     # 'data/datasets=affectnet_desktop',
        #     # 'data/augmentations=default',
        #
        # ]
        # deca_conf = None
        # deca_conf_path = None
        # fixed_overrides_deca = None
        # stage = None
        # deca_default = None
        # deca_overrides = None
        #

        #2 EMODECA
        emodeca_default = "emodeca_emonet_coarse"
        emodeca_overrides = ['learning/logging=none',
                             'model/settings=coarse_emodeca',
                             # 'model/settings=coarse_emodeca_emonet',
                             # '+model.mlp_norm_layer=BatchNorm1d',
                             # 'model.unpose_global_emonet=false',
                             # 'model.use_coarse_image_emonet=false',
                             # 'model.use_detail_image_emonet=true',
                             # 'model.static_cam_emonet=false',
                             # 'model.static_light=false',

                             'model.mlp_dimension_factor=4',
                             ]

        # deca_default = "deca_train_coarse_cluster"
        # deca_overrides = [
        #     # 'model/settings=coarse_train',
        #     'model/settings=detail_train',
        #     'model/paths=desktop',
        #     'model/flame_tex=bfm_desktop',
        #     'model.resume_training=True',  # load the original DECA model
        #     'model.useSeg=rend', 'model.idw=0',
        #     'learning/batching=single_gpu_coarse',
        #     'learning/logging=none',
        #     # 'learning/batching=single_gpu_detail',
        #     #  'model.shape_constrain_type=None',
        #      'model.detail_constrain_type=None',
        #     'data/datasets=affectnet_cluster',
        #      'learning.batch_size_test=1'
        # ]
        # # deca_conf_path = None
        # # stage = None



        deca_default = None
        deca_overrides = None
        deca_conf_path = "/home/rdanecek/Workspace/mount/scratch/rdanecek/emoca/finetune_deca/2021_04_19_18-59-19_ExpDECA_Affec_para_Jaw_NoRing_EmoLossB_F2VAEw-0.00150_DeSegrend_DwC_early"
        # deca_conf_path = "/run/user/1001/gvfs/smb-share:server=ps-access.is.localnet,share=scratch/rdanecek/emoca/finetune_deca/2021_04_19_18-59-19_ExpDECA_Affec_para_Jaw_NoRing_EmoLossB_F2VAEw-0.00150_DeSegrend_DwC_early"
        # deca_conf = None
        stage = 'detail'

        relative_to_path = '/ps/scratch/'
        # # replace_root_path = '/run/user/1001/gvfs/smb-share:server=ps-access.is.localnet,share=scratch/'
        replace_root_path = '/home/rdanecek/Workspace/mount/scratch/'

        # replace_root_path = None
        # relative_to_path = None

        # emodeca_default = "emonet"
        # emodeca_overrides = ['model/settings=emonet_trainable']
        # deca_default = None
        # deca_overrides = None
        # deca_conf_path = None
        # stage = None
        # relative_to_path = None
        # replace_root_path = None

        #3) EmoSWIN
        emodeca_default = "emoswin"
        emodeca_overrides = [
            # 'model/settings=emonet_trainable',
            'model/settings=swin',
            'learning/logging=none',
            # 'learning.max_steps=1',
            'learning.max_epochs=1',
            'learning.checkpoint_after_training=latest',
            # 'learning.batch_size_train=32',
            # 'learning.batch_size_val=1',
            # '+learning/lr_scheduler=reduce_on_plateau',
            # 'model.continuous_va_balancing=1d',
            # 'model.continuous_va_balancing=2d',
            # 'model.continuous_va_balancing=expr',
            # 'learning.val_check_interval=1',
            # 'learning.learning_rate=0',
            # 'learning/optimizer=adabound',
            # 'data/datasets=affectnet_desktop',
            # 'data/augmentations=default',
        ]
        deca_conf = None
        deca_conf_path = None
        fixed_overrides_deca = None
        stage = None
        deca_default = None
        deca_overrides = None

        cfg = configure(emodeca_default,
                        emodeca_overrides,
                        deca_default,
                        deca_overrides,
                        deca_conf_path=deca_conf_path,
                        deca_stage=stage,
                        relative_to_path=relative_to_path,
                        replace_root_path=replace_root_path)
    else:
        cfg_path = sys.argv[1]
        print(f"Training from config '{cfg_path}'")
        with open(cfg_path, 'r') as f:
            cfg = OmegaConf.load(f)

    train_emodeca(cfg, 0)


if __name__ == "__main__":
    main()