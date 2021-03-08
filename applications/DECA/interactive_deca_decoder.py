from models.DECA import DecaModule
from omegaconf import OmegaConf, DictConfig
from pathlib import Path
from applications.DECA.train_deca_modular import find_checkpoint
from applications.DECA.test_and_finetune_deca import prepare_data
import torch
import matplotlib.pyplot as plt


def hack_paths(cfg, replace_root_path=None, relative_to_path=None):
    if relative_to_path is not None and replace_root_path is not None:
        cfg.model.flame_model_path = str(Path(replace_root_path) / Path(cfg.model.flame_model_path).relative_to(relative_to_path))
        cfg.model.flame_lmk_embedding_path = str(Path(replace_root_path) / Path(cfg.model.flame_lmk_embedding_path).relative_to(relative_to_path))
        cfg.model.tex_path = str(Path(replace_root_path) / Path(cfg.model.tex_path).relative_to(relative_to_path))
        cfg.model.topology_path = str(Path(replace_root_path) / Path(cfg.model.topology_path).relative_to(relative_to_path))
        cfg.model.face_mask_path = str(Path(replace_root_path) / Path(cfg.model.face_mask_path).relative_to(relative_to_path))
        cfg.model.face_eye_mask_path = str(Path(replace_root_path) / Path(cfg.model.face_eye_mask_path).relative_to(relative_to_path))
        cfg.model.fixed_displacement_path = str(Path(replace_root_path) / Path(cfg.model.fixed_displacement_path).relative_to(relative_to_path))
        cfg.model.pretrained_vgg_face_path = str(Path(replace_root_path) / Path(cfg.model.pretrained_vgg_face_path).relative_to(relative_to_path))

        cfg.data.data_root = str(Path(replace_root_path) / Path(cfg.data.data_root).relative_to(relative_to_path))

    return cfg



def load_deca_and_data(path_to_models=None,
                       run_name=None,
                       stage=None,
                       relative_to_path = None,
                       replace_root_path = None,
                       mode='best'):

    run_path = Path(path_to_models) / run_name
    with open(Path(run_path) / "cfg.yaml", "r") as f:
        conf = OmegaConf.load(f)

    cfg = conf[stage]

    if relative_to_path is not None and replace_root_path is not None:
        checkpoint = find_checkpoint(cfg, replace_root_path, relative_to_path, mode=mode)
        print(f"Loading checkpoint '{checkpoint}'")
        cfg = hack_paths(cfg, replace_root_path=replace_root_path, relative_to_path=relative_to_path)

    cfg.model.resume_training = False
    checkpoint_kwargs = {
        "model_params": cfg.model,
        "learning_params": cfg.learning,
        "inout_params": cfg.inout,
        "stage_name": "testing",
    }
    deca = DecaModule.load_from_checkpoint(checkpoint_path=checkpoint, **checkpoint_kwargs)
    train_or_test = 'test'
    if train_or_test == 'train':
        mode = True
    else:
        mode = False
    prefix = stage
    deca.reconfigure(cfg.model, cfg.inout, prefix, downgrade_ok=True, train=mode)


    dm, name = prepare_data(cfg)
    dm.setup()
    deca.cuda()
    deca.eval()
    print("DECA loaded")
    return deca, dm


def test(deca, dm, image_index = None, values = None):
    if image_index is None and values is None:
        raise ValueError("Specify either an image to encode-decode or values to decode.")
    test_set = dm.test_set
    # image_index = 0

    if image_index is not None:
        image_index = image_index
        batch = test_set[image_index]
        for key, val in batch.items():
            if isinstance(val, torch.Tensor):
                batch[key] = val.cuda()
        with torch.no_grad():
            values = deca._encode(batch, training=False)

    with torch.no_grad():
        values = deca._decode(values, training=False)
        losses_and_metrics = deca.compute_loss(values, training=False)

    uv_detail_normals = None
    if 'uv_detail_normals' in values.keys():
        uv_detail_normals = values['uv_detail_normals']
    visualizations, grid_image = deca._visualization_checkpoint(values['verts'], values['trans_verts'], values['ops'],
                                                                uv_detail_normals, values, 0, "",
                                                                "", save=False)
    vis_dict = deca._log_visualizations("", visualizations, values, 0, indices=0)

    return values, vis_dict

    # predicted_images = values['predicted_images']
    # predicted_detailed_image = values['predicted_detailed_image']


def plot_results(vis_dict, title, detail=True):
    # plt.figure()

    # plt.subplot(pos, **kwargs)
    # plt.subplot(**kwargs)
    # plt.subplot(ax)

    if detail:
        fig, axs = plt.subplots(1, 8)
        axs[0].imshow(vis_dict['detail_detail__inputs'])
        axs[1].imshow(vis_dict['detail_detail__landmarks_gt'])
        axs[2].imshow(vis_dict['detail_detail__landmarks_predicted'])
        axs[3].imshow(vis_dict['detail_detail__mask'])
        axs[4].imshow(vis_dict['detail_detail__geometry_coarse'])
        axs[5].imshow(vis_dict['detail_detail__geometry_detail'])
        axs[6].imshow(vis_dict['detail_detail__output_images_coarse'])
        axs[7].imshow(vis_dict['detail_detail__output_images_detail'])
    else:
        fig, axs = plt.subplots(1, 6)
        axs[0].imshow(vis_dict['coarse_coarse__inputs'])
        axs[1].imshow(vis_dict['coarse_coarse__landmarks_gt'])
        axs[2].imshow(vis_dict['coarse_coarse__landmarks_predicted'])
        axs[3].imshow(vis_dict['coarse_coarse__mask'])
        axs[4].imshow(vis_dict['coarse_coarse__geometry_coarse'])
        axs[5].imshow(vis_dict['coarse_coarse__output_images_coarse'])

    # axs[0,0].imshow(vis_dict['detail_detail__inputs'])
    # axs[0,1].imshow(vis_dict['detail_detail__landmarks_gt'])
    # axs[0,2].imshow(vis_dict['detail_detail__landmarks_predicted'])
    # axs[0,3].imshow(vis_dict['detail_detail__mask'])
    # axs[0,4].imshow(vis_dict['detail_detail__geometry_coarse'])
    # axs[0,5].imshow(vis_dict['detail_detail__geometry_detail'])
    # axs[0,6].imshow(vis_dict['detail_detail__output_images_coarse'])
    # axs[0,7].imshow(vis_dict['detail_detail__output_images_detail'])
    # axs[6].imshow(vis_dict['detail_detail__landmarks_predicted'])
    # axs[7].imshow(vis_dict['detail_detail__landmarks_predicted'])
    # axs[8].imshow(vis_dict['detail_detail__landmarks_predicted'])
    # axs[9].imshow(vis_dict['detail_detail__landmarks_predicted'])
    # axs[10].imshow(vis_dict['detail_detail__landmarks_predicted'])

    # plt.title(title)
    fig.suptitle(title)

    plt.show()
    #


def main():
    path_to_models = '/home/rdanecek/Workspace/mount/scratch/rdanecek/emoca/finetune_deca'
    # run_name = '2021_03_01_11-31-57_VA_Set_videos_Train_Set_119-30-848x480.mp4_EmoNetLossB_F1F2VAECw-0.00150_CoSegmentGT_DeSegmentRend'
    run_name =  '2021_03_01_11-31-57_VA_Set_videos_Train_Set_119-30-848x480.mp4_EmoNetLossB_F1F2VAECw-0.00150_CoSegmentGT_DeSegmentRend'
    stage = 'detail'
    relative_to_path = '/ps/scratch/'
    replace_root_path = '/home/rdanecek/Workspace/mount/scratch/'
    deca, dm = load_deca_and_data(path_to_models, run_name, stage, relative_to_path, replace_root_path)
    image_index = 390*4

    values, visdict = test(deca, dm, image_index)

    plot_results(visdict, "title")



if __name__ == "__main__":
    main()