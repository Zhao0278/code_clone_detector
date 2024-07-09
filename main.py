import json
import os

from sklearn.metrics import classification_report
from tqdm import tqdm
from code_window import CodeWindow
from clone_detect import find_similar_code_segment
from utils import *



def add_label_bracket(labels: list[str]) -> list[str]:
    return ['<' + label + '>' for label in labels]

def is_all_keep(labels: list[str]) -> bool:
    for label in labels:
        if label != '<keep>':
            return False
    return True

def to_str(labels: list[str]) -> str:
    s = ''
    for label in labels:
        s = s + '\t' + label
    return s

def to_idx(labels: list[str], target_names: list[str]) -> list[int]:
    name_map = {}
    for idx, name in enumerate(target_names):
        name_map[name] = idx
    label_idx = []
    for label in labels:
        label_idx.append(name_map[label])
    return label_idx



if __name__ == '__main__':
    
    data_dir = './data/test_2'
    file_prefix = data_dir + '/test_2'
    
    file_path = file_prefix + '.json'
    file_wpe_path = file_prefix + '_with_prior_edit.json'
    file_wccd_path = file_prefix + '_with_codeclone_detect.json'
    gold_path = file_prefix + '.gold'
    ccd_path = file_prefix + '.ccd'


    if os.path.exists(file_wpe_path):
        with open(file_wpe_path, 'r') as f:
            dataset_wpe = json.load(f)
    else:
        # 给每个sliding window提取相关的prior edit
        # 6 label转3 label
        with open(file_path, 'r') as f:
            dataset = json.load(f)

        dataset_wpe = dataset
        for commit_url, commit in tqdm(dataset.items()):
            hunks_wol, sliding_windows_wpe = [], []
            for hk_idx, raw_hunk in enumerate(commit['hunks']):
                raw_hunk['old_labels'] = label_conversion(inline_labels=add_label_bracket(raw_hunk['inline_labels']), 
                                                          inter_labels=add_label_bracket(raw_hunk['inter_labels']))
                hunks_wol.append(raw_hunk)

            hunks = [CodeWindow(hunk, 'hunk') for hunk in commit['hunks']]
            for sw_idx, raw_sw in enumerate(commit['sliding_windows']):
                sw = CodeWindow(raw_sw, 'sliding_window')
                raw_sw['old_labels'] = label_conversion(inline_labels=add_label_bracket(sw.inline_labels), 
                                                        inter_labels=add_label_bracket(sw.inter_labels))
                # find prior edit
                # 不考虑overlap hunk
                hunks_woo = []
                for hunk in hunks:
                    if hunk.id not in sw.overlap_hunk_ids:
                        hunks_woo.append(hunk)
                prior_edit = select_prior_edits(sw, hunks_woo)
                raw_sw['prior_edit_id'] = prior_edit.id
                sliding_windows_wpe.append(raw_sw)

            dataset_wpe[commit_url]['hunks'] = hunks_wol 
            dataset_wpe[commit_url]['sliding_windows'] = sliding_windows_wpe  
        with open(file_wpe_path, 'w') as f:
            json.dump(dataset_wpe, f)



    if os.path.exists(file_wccd_path):
        with open(file_wccd_path, 'r') as f:
            dataset_wccd = json.load(f)
    else:
        # 搜索每个sliding window中的code clone
        dataset_wccd = dataset_wpe
        for commit_url, commit in tqdm(dataset_wpe.items()):
            hunks = commit['hunks']
            sliding_windows = commit['sliding_windows']
            sliding_windows_wccd = []
            for sw_idx, sw in enumerate(sliding_windows):
                prior_edit = hunks[sw['prior_edit_id']]
                hunk = CodeWindow(prior_edit, 'hunk')
                hunk_before_edit = hunk.before_edit_window()
                labels = prior_edit['old_labels']
                assert len(hunk_before_edit) == len(labels)

                cc_score = [0 for i in range(len(sw['code_window']))]
                cc_result = ['<keep>' for i in range(len(sw['code_window']))]
                document = ''.join(sw['code_window'])

                for (line, label) in zip(hunk_before_edit, labels):
                    if label == '<replace>':
                        # replace类型:
                        # hunk的before_edit_region作为query，sliding_window作为document
                        # 若存在clone，检测到的行标为<replace>
                        found_segments = find_similar_code_segment(line, document)
                        for segment in found_segments:
                            for line_idx in segment['matched_lines']:
                                cc_result[line_idx] = '<replace>'
                                cc_score[line_idx] = segment['score']
                    elif label == '<add>':
                        # insert类型:
                        # hunk的prefix作为query，sliding_window作为document
                        # 若存在clone，检测到的行标为<insert>/<add>
                        found_segments = find_similar_code_segment(line, document)
                        for segment in found_segments:
                            for line_idx in segment['matched_lines']:
                                cc_result[line_idx] = '<add>'
                                cc_score[line_idx] = segment['score']
                
                sw['code_clone_score'] = cc_score
                sw['code_clone_result'] = cc_result
                sliding_windows_wccd.append(sw)
            dataset_wccd[commit_url]['sliding_windows'] = sliding_windows_wccd
        with open(file_wccd_path, 'w') as f:
                json.dump(dataset_wccd, f)


    if os.path.exists(gold_path) == False:    
        with open(gold_path, "w") as f:
            for commit_url, commit in dataset_wccd.items():
                sliding_windows = commit['sliding_windows']
                for sw_idx, sw in enumerate(sliding_windows):
                    f.write(to_str(sw['old_labels']) + "\n")
    if os.path.exists(ccd_path) == False:    
        with open(ccd_path, "w") as f:
            for commit_url, commit in dataset_wccd.items():
                sliding_windows = commit['sliding_windows']
                for sw_idx, sw in enumerate(sliding_windows):
                    f.write(to_str(sw['code_clone_result']) + "\n")

    all_labels = []
    all_results = []
    for commit_url, commit in tqdm(dataset_wccd.items()):
        sliding_windows = commit['sliding_windows']
        for sw_idx, sw in enumerate(sliding_windows):
            all_labels = all_labels + sw['old_labels']
            all_results = all_results + sw['code_clone_result']
    target_names = ['<keep>', '<replace>', '<add>']
    all_labels = to_idx(all_labels, target_names)
    all_results = to_idx(all_results, target_names)
    print(classification_report(all_labels, all_results, target_names=target_names))
    