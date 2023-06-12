import os

import abc
import numpy as np
import pandas as pd
import torch

from deeplabcut.generate_training_dataset.trainingsetmanipulation import read_image_shape_fast
from deeplabcut.pose_estimation_tensorflow.lib.trackingutils import calc_bboxes_from_keypoints


# Shaokai's function
def df2generic(proj_root, df, image_id_offset = 0):

    try:
        individuals = df.columns.get_level_values('individuals').unique().tolist()
    except KeyError:
        new_cols = pd.MultiIndex.from_tuples(
            [(col[0], 'single', col[1], col[2]) for col in df.columns],
            names=['scorer', 'individuals', 'bodyparts', 'coords']
        )
        df.columns = new_cols

        individuals = df.columns.get_level_values('individuals').unique().tolist()
    
    unique_bpts = []

    if 'single' in individuals:
        unique_bpts.extend(
            df
            .xs('single', level='individuals', axis=1)
            .columns.get_level_values('bodyparts').unique()
        )
    multi_bpts = (
                df
        .xs(individuals[0], level='individuals', axis=1)
        .columns.get_level_values('bodyparts').unique().tolist()
    )
    
    coco_categories = []

    # assuming all individuals have the same name and same category id

    individual = individuals[0]
    
    category = {
        "name": individual,
        "id": 0,
        "supercategory": "animal",
        
    }

    if individual == 'single':
        category['keypoints'] = unique_bpts
    else:
        category['keypoints'] = multi_bpts
    
    coco_categories.append(category)
    
    coco_images = []
    coco_annotations = []    

    annotation_id = 0
    image_id = -1
    for _, file_name in enumerate(df.index):
        data = df.loc[file_name]            

        # skipping all nan
        # if np.isnan(data.to_numpy()).all():
        #     continue
        
        image_id+=1
        
        for individual_id, individual in enumerate(individuals):
            category_id = 0 
            try:                
                kpts = data.xs(individual, level='individuals').to_numpy().reshape((-1, 2))
            except:
                # somehow there are duplicates. So only use the first occurence
                data = data.iloc[0] 
                kpts = data.xs(individual, level='individuals').to_numpy().reshape((-1, 2))           
            
            keypoints = np.zeros((len(kpts),3))
            
            keypoints[:,:2] = kpts
            
            is_visible = ~pd.isnull(kpts).all(axis=1)
            
            keypoints[:, 2] = np.where(is_visible, 2, 0)
            
            num_keypoints = is_visible.sum()

            bbox_margin = 20
            
            xmin, ymin, xmax, ymax = calc_bboxes_from_keypoints(
                [keypoints], slack=bbox_margin,
            )[0][:4]
                        
            w = xmax - xmin
            h = ymax - ymin
            area = w * h
            bbox = np.nan_to_num([xmin, ymin, w, h])
            keypoints = np.nan_to_num(keypoints.flatten())
                                
            annotation_id += 1
            annotation = {
                "image_id": image_id + image_id_offset,
                "num_keypoints": num_keypoints,
                "keypoints": keypoints,
                "id": annotation_id,
                "category_id": category_id,
                "area": area,
                "bbox": bbox,
                "iscrowd": 0,
            }

            # adds an annotaion even if no keypoint is annotated for the current individual
            # This is not standard for COCO but is useful because each image will then have
            # the same number of annotations (i.e possible to train with batches without overcomplicating the code)
            coco_annotations.append(annotation)

        # I think width and height are important

        if isinstance(file_name, tuple):
            image_path = os.path.join(proj_root, *list(file_name))
        else:
            image_path = os.path.join(proj_root, file_name)

        
        _, height, width = read_image_shape_fast(image_path)
        
        
        image = {'file_name' : image_path,
                    "width": width,
                    "height": height,
                    'id': image_id + image_id_offset
                    }
        coco_images.append(image)

    ret_obj = {'images': coco_images,
                'annotations': coco_annotations,
                'categories': coco_categories,
                }
    return ret_obj


def create_folder(path_to_folder):
    """Creates all folders contained in the path.
    Parameters
    ----------
    path_to_folder : str
        Path to the folder that should be created
    """
    if not os.path.exists(path_to_folder):
        os.makedirs(path_to_folder)


def fix_seeds(seed: int):
    """
    Fixes seed for all random functions
    @param seed: int
        Seed to be fixed
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

def is_seq_of(seq, expected_type, seq_type=None):
    """Check whether it is a sequence of some type.
    Args:
        seq (Sequence): The sequence to be checked.
        expected_type (type): Expected type of sequence items.
        seq_type (type, optional): Expected sequence type.
    Returns:
        bool: Whether the sequence is valid.
    """
    if seq_type is None:
        exp_seq_type = abc.Sequence
    else:
        assert isinstance(seq_type, type)
        exp_seq_type = seq_type
    if not isinstance(seq, exp_seq_type):
        return False
    for item in seq:
        if not isinstance(item, expected_type):
            return False
    return True