from utils.condor import execute_on_cluster
from pathlib import Path
import resume_expdeca_training
import datetime
from omegaconf import OmegaConf
import time as t

def submit(
        resume_folder,
        stage,
        resume_from_previous,
        force_new_location,
        bid=10):

    cluster_repo_path = "/home/rdanecek/workspace/repos/gdl"
    submission_dir_local_mount = "/home/rdanecek/Workspace/mount/scratch/rdanecek/emoca/submission"
    submission_dir_cluster_side = "/ps/scratch/rdanecek/emoca/submission"
    result_dir_local_mount = "/home/rdanecek/Workspace/mount/scratch/rdanecek/emoca/finetune_deca"
    result_dir_cluster_side = "/ps/scratch/rdanecek/emoca/finetune_deca"
    time = datetime.datetime.now().strftime("%Y_%m_%d_%H-%M-%S")
    submission_folder_name = time + "_" + "submission"
    submission_folder_local = Path(submission_dir_local_mount) / submission_folder_name
    submission_folder_cluster = Path(submission_dir_cluster_side) / submission_folder_name

    local_script_path = Path(resume_expdeca_training.__file__).absolute()
    cluster_script_path = Path(cluster_repo_path) / local_script_path.parents[1].name \
                          / local_script_path.parents[0].name / local_script_path.name


    coarse_file = Path(result_dir_local_mount) / resume_folder / "cfg.yaml"
    with open(coarse_file, 'r') as f:
        cfg = OmegaConf.load(f)
    cfg_coarse = cfg.coarse

    submission_folder_local.mkdir(parents=True)
    # python_bin = 'python'
    python_bin = '/home/rdanecek/anaconda3/envs/<<ENV>>/bin/python'
    username = 'rdanecek'
    gpu_mem_requirement_mb = cfg_coarse.learning.gpu_memory_min_gb * 1024
    # gpu_mem_requirement_mb = None
    # cpus = cfg_coarse.data.num_workers + 2 # 1 for the training script, 1 for wandb or other loggers (and other stuff), the rest of data loading
    cpus = 2 # 1 for the training script, 1 for wandb or other loggers (and other stuff), the rest of data loading
    gpus = cfg_coarse.learning.num_gpus
    num_jobs = 1
    max_time_h = 36
    max_price = 10000
    job_name = "train_deca"
    cuda_capability_requirement = 6
    mem_gb = 40
    args = f"{str(Path(result_dir_cluster_side) / resume_folder)} {stage} {int(resume_from_previous)} {int(force_new_location)}"

    execute_on_cluster(str(cluster_script_path),
                       args,
                       str(submission_folder_local),
                       str(submission_folder_cluster),
                       str(cluster_repo_path),
                       python_bin=python_bin,
                       username=username,
                       gpu_mem_requirement_mb=gpu_mem_requirement_mb,
                       cpus=cpus,
                       mem_gb=mem_gb,
                       gpus=gpus,
                       num_jobs=num_jobs,
                       bid=bid,
                       max_time_h=max_time_h,
                       max_price=max_price,
                       job_name=job_name,
                       cuda_capability_requirement=cuda_capability_requirement
                       )
    t.sleep(1)


def main():
    stage = 0
    resume_from_previous = False
    force_new_location = False

    resume_folders = []
    # resume_folders += ['2021_04_13_19-02-10_ExpDECA__EmoTrain_Jaw_DeSegrend_early'] # has been resumed, will crash on detail, will have to be resumed again
    # resume_folders += ['2021_04_13_19-02-11_ExpDECA__EmoStat_Jaw_DeSegrend_early'] # has been resumed, will crash on detail, will have to be resumed again
    # resume_folders += ['2021_04_13_19-02-31_ExpDECA__clone_Jaw_DeSegrend_early'] # has been resumed, will crash on detail, will have to be resumed again
    # resume_folders += ['2021_04_13_18-54-34_ExpDECA__para_Jaw_DeSegrend_early'] # has been resumed, will crash on detail, will have to be resumed again
    # resume_folders += ['2021_04_13_18-47-00_ExpDECA__para_DeSegrend_early'] # has been resumed, will crash on detail, will have to be resumed again, was resumed again
    # resume_folders += ['2021_04_13_18-39-24_ExpDECA__para_Jaw_DeSegrend_early'] # has been resumed, will crash on detail, will have to be resumed again
    # resume_folders += ['2021_04_14_14-00-16_ExpDECA__para_Jaw_NoRing_DeSegrend_CoNone_DeNone_early']
    # resume_folders += ['2021_04_14_17-39-46_ExpDECA_para_Jaw_NoRing_DeSegrend_CoNone_DeNone_early']
    # resume_folders += ['2021_04_14_18-10-36_ExpDECA_para_Jaw_NoRing_DeSegrend_CoNone_DeNone_Aug_early']
    # resume_folders += ['2021_04_14_22-49-50_ExpDECA_para_Jaw_NoRing_DeSegrend_CoNone_DeNone_early']
    # resume_folders += ['2021_04_14_23-02-10_ExpDECA_para_Jaw_NoRing_DeSegrend_CoNone_DeNone_early']

    # for resume_folder in resume_folders:
    #     submit(resume_folder, stage, resume_from_previous, force_new_location)

    stage = 2
    resume_from_previous = False
    force_new_location = False

    resume_folders = []
    # resume_folders += ['2021_04_18_13-43-32_ExpDECA_para_Jaw_NoRing_EmoLossB_F2VAEw-0.00150_DeSegrend_CoNone_DeNone_DwC_early'] # resumed
    # resume_folders += ['2021_04_18_13-43-46_ExpDECA_para_Jaw_NoRing_EmoLossB_F2VAEw-0.00150_DeSegrend_CoNone_DeNone_DwC_early'] # resumed
    # resume_folders += ['2021_04_18_13-43-55_ExpDECA_para_Jaw_NoRing_EmoLossB_F2VAEw-0.00150_DeSegrend_CoNone_DeNone_Aug_early'] # resumed
    # resume_folders += ['2021_04_18_12-47-40_ExpDECA_para_Jaw_NoRing_DeSegrend_CoNone_DeNone_DwC_early'] # resumed
    for resume_folder in resume_folders:
        submit(resume_folder, stage, resume_from_previous, force_new_location)



if __name__ == "__main__":
    main()