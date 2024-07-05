import json
import os

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



if __name__ == '__main__':
    
    file_prefix = 'test'
    file_path = file_prefix + '.json'
    file_wpe_path = file_prefix + '_with_prior_edit.json'
    file_wccd_path = file_prefix + '_with_codeclone_detect.json'


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
            hunks = [CodeWindow(hunk, 'hunk') for hunk in commit['hunks']]
            sliding_windows = commit['sliding_windows']
            hunks_wol, sliding_windows_wpe = [], []
            for hk_idx, hunk in enumerate(hunks):
                hk_wol = {}
                hk_wol["id"] = hunk.id
                hk_wol["code_window"] = hunk.code_window
                hk_wol['old_labels'] = label_conversion(inline_labels=add_label_bracket(hunk.inline_labels), 
                                                        inter_labels=add_label_bracket(hunk.inter_labels))
                hk_wol["after_edit"] = hunk.after_edit
                hk_wol["type"] = hunk.edit_type
                hk_wol["file_path"] = hunk.file_path
                hk_wol["edit_start_line_idx"] = hunk.edit_start_line_idx
                hunks_wol.append(hk_wol)

            for sw_idx, raw_sw in enumerate(sliding_windows):
                sw = CodeWindow(raw_sw, 'sliding_window')
                sw_wpe = {}
                sw_wpe['code_window'] = sw.code_window
                sw_wpe['old_labels'] = label_conversion(inline_labels=add_label_bracket(sw.inline_labels), 
                                                        inter_labels=add_label_bracket(sw.inter_labels))
                sw_wpe["sliding_window_type"] = sw.sliding_window_type
                sw_wpe["overlap_hunk_ids"] = sw.overlap_hunk_ids
                sw_wpe["file_path"] = sw.file_path
                sw_wpe["edit_start_line_idx"] = sw.edit_start_line_idx
                # find prior edit
                prior_edit = select_prior_edits(sw, hunks)
                sw_wpe['prior_edit_id'] = prior_edit.id
                sliding_windows_wpe.append(sw_wpe)

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
                # 排除overlap hunk
                if sw['prior_edit_id'] in sw['overlap_hunk_ids']:
                    continue

                prior_edit = hunks[sw['prior_edit_id']]
                labels = prior_edit['old_labels']
                blocks = prior_edit['code_window']
                # print('--sliding window:',sw_idx, '--hunk:', sw['prior_edit_id'], '(', len(blocks), ',', len(labels), ')')
                # print(labels)

                cc_score = [0 for i in range(len(sw['code_window']))]
                cc_result = ['<keep>' for i in range(len(sw['code_window']))]
                document = ''.join(sw['code_window'])
                block_idx, label_idx = 0, 0

                while label_idx < len(labels):
                    # print('----', block_idx, label_idx)
                    block = blocks[block_idx]
                    label = labels[label_idx]

                    # 如果有多余insert block，跳过去
                    if isinstance(block, dict) and block['block_type'] == 'insert':
                        block_idx = block_idx + 1
                        continue

                    if label == '<replace>':
                        # replace类型:
                        # hunk的before_edit_region作为query，sliding_window作为document
                        # 若存在clone，检测到的行标为<replace>
                        if isinstance(block, dict):
                            assert block['block_type'] == 'modify' or block['block_type'] == 'delete'
                            query = ''.join(block['before'])
                            line_count = len(block['before'])   # 跳过block中before的行数
                        else:
                            query = block
                            line_count = 1
                        found_segments = find_similar_code_segment(query, document)
                        for segment in found_segments:
                            for line_idx in segment['matched_lines']:
                                cc_result[line_idx] = '<replace>'
                                cc_score[line_idx] = segment['score']
                        block_idx = block_idx + 1
                        label_idx = label_idx + line_count
                    elif label == '<add>':
                        # insert类型:
                        # hunk的prefix作为query，sliding_window作为document
                        # 若存在clone，检测到的行标为<insert>
                        assert isinstance(block, str)
                        found_segments = find_similar_code_segment(block, document)
                        for segment in found_segments:
                            for line_idx in segment['matched_lines']:
                                cc_result[line_idx] = '<insert>'
                                cc_score[line_idx] = segment['score']
                        block_idx = block_idx + 1
                        label_idx = label_idx + 1
                    else:
                        block_idx = block_idx + 1
                        label_idx = label_idx + 1
                
                sw['code_clone_score'] = cc_score
                sw['code_clone_result'] = cc_result
                sliding_windows_wccd.append(sw)
            dataset_wccd[commit_url]['sliding_windows'] = sliding_windows_wccd
        with open(file_wccd_path, 'w') as f:
                json.dump(dataset_wccd, f)


    count = 0
    correct = 0
    correct_not_trivial = 0
    for commit_url, commit in dataset_wccd.items():
        sliding_windows = commit['sliding_windows']
        for sw_idx, sw in enumerate(sliding_windows):
           count = count + 1
           if sw['old_labels'] == sw['code_clone_result']:
                correct = correct + 1
                if is_all_keep(sw['old_labels']) == False:
                    correct_not_trivial = correct_not_trivial + 1
    print(count, correct, correct_not_trivial)
    