from affectnet_validation import *



def main():
    # path_to_models = '/home/rdanecek/Workspace/mount/scratch/rdanecek/emoca/finetune_deca'
    # # path_to_models = '/ps/scratch/rdanecek/emoca/finetune_deca'
    #
    path_to_affectnet = "/home/rdanecek/Workspace/mount/project/EmotionalFacialAnimation/data/affectnet/"
    # path_to_processed_affectnet = "/home/rdanecek/Workspace/mount/scratch/rdanecek/data/affectnet/"

    path_to_models = '/is/cluster/work/rdanecek/emoca/finetune_deca'
    # path_to_affectnet = "/ps/project/EmotionalFacialAnimation/data/affectnet/"
    # path_to_processed_affectnet = "/ps/scratch/rdanecek/data/affectnet/"
    path_to_processed_affectnet = "/is/cluster/work/rdanecek/data/affectnet/"

    run_names = []
    # run_names += ['2021_03_25_19-42-13_DECA_training'] # DECA EmoNet
    # run_names += ['2021_03_29_23-14-42_DECA__EmoLossB_F2VAEw-0.00150_DeSegFalse_early'] # DECA EmoNet 2
    # run_names += ['2021_03_18_21-10-25_DECA_training'] # Basic DECA
    # run_names += ['2021_03_26_15-05-56_DECA__DeSegFalse_DwC_early'] # Detail with coarse
    # run_names += ['2021_03_26_14-36-03_DECA__DeSegFalse_DeNone_early'] # No detail exchange
    # run_names += ['2021_05_21_15-44-45_ExpDECA_Affec_para_Jaw_NoRing_DeSegrend_Exnone_MLP_0.005_early'] # DECA MLP
    run_names += ['2021_06_01_15-02-35_ExpDECA_Affec_para_Jaw_NoRing_DeSegrend_Exnone_MLP_1.0_detJ_DwC_early/'] # DECA MLP

    mode = 'detail'
    # mode = 'coarse'

    for run_name in run_names:
        print(f"Beginning testing for '{run_name}' in mode '{mode}'")
        relative_to_path = '/ps/scratch/'
        replace_root_path = '/home/rdanecek/Workspace/mount/scratch/'
        deca, conf = load_model(path_to_models, run_name, mode, relative_to_path, replace_root_path)
        # deca, conf = load_model(path_to_models, run_name, mode)

        # deca.deca.config.resume_training = True
        # deca.deca._load_old_checkpoint()
        # run_name = "Original_DECA"

        deca.eval()

        import datetime
        time = datetime.datetime.now().strftime("%Y_%m_%d_%H-%M-%S")
        conf[mode].inout.random_id = str(hash(time))
        conf[mode].learning.logger_type = None
        conf['detail'].learning.logger_type = None
        conf['coarse'].learning.logger_type = None
        # conf['detail'].data.root_dir = "/home/rdanecek/Workspace/mount/project/EmotionalFacialAnimation/data/affectnet/"
        # conf['coarse'].data.root_dir = "/home/rdanecek/Workspace/mount/project/EmotionalFacialAnimation/data/affectnet/"
        # conf[mode].data.root_dir = "/home/rdanecek/Workspace/mount/project/EmotionalFacialAnimation/data/affectnet/"

        dm = data_preparation_function(conf[mode], path_to_affectnet, path_to_processed_affectnet)
        conf[mode].model.test_vis_frequency = 1
        conf[mode].inout.name = "affectnet_test_" + conf[mode].inout.name
        # conf[mode].inout.name = "Original_DECA"
        single_stage_deca_pass(deca, conf[mode], stage="test", prefix="affect_net", dm=dm)
        print("We're done y'all")


if __name__ == '__main__':
    main()