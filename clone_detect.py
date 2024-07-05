from rapidfuzz import fuzz
import subprocess

def find_line_numbers(start_char_pos, end_char_pos, document_in_lines):
    line_idx = []  # 用来存储包含起始和结束字符的行号
    current_char_count = 0  # 当前字符总数，用于确定字符位置
    
    for index, line in enumerate(document_in_lines):
        line_length = len(line)
        next_char_count = current_char_count + line_length  # 下一个位置的字符总数
        
        if start_char_pos < next_char_count and end_char_pos > current_char_count:
            start = max(start_char_pos, current_char_count)
            end = min(next_char_count, next_char_count)

            # 计算交集的大小
            intersection_length = max(0, end - start + 1)
            if intersection_length / len(line) > 0.75:
                line_idx.append(index)
        
        current_char_count = next_char_count  # 更新当前的字符总数                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         
    
    return line_idx#[1:-1]


def partial_scs(query, document, threshold, left, right):
    result = fuzz.partial_ratio_alignment(query, document, score_cutoff=threshold)
    if result is None or (result.src_end - result.src_start) / len(query) < 0.75:
        return []
    start_char = left + result.dest_start
    end_char = left + result.dest_end
    segments = [{
        'score': result.score,
        'start_char': start_char,
        'end_char': end_char
    }]
    left_segments = partial_scs(query, document[left : start_char], threshold, left=left, right=start_char)
    right_segments = partial_scs(query, document[end_char : right], threshold, left=end_char, right=right)
    return left_segments + segments + right_segments
    

def find_similar_code_segment(query, document, threshold=80):
    """
    Func:
        Find all similar code segments in the document
    Args:
        query: str, the code segment to search
        document: str, the document to search in
        threshold: int, the similarity threshold
    Returns:
        found_segments: list, a list of found segments
                        {
                            "score": int, the similarity score,
                            "matched_lines": list, a list of line numbers where the code is found, indexed from 0
                        }
    """
    found_segments = []
    original_document = document
    original_document_lines = original_document.splitlines(keepends=True)

    char_segments = partial_scs(query, document, threshold, left=0, right=len(document))
    for segment in char_segments:
        found_line_range = find_line_numbers(segment['start_char'], segment['end_char'], original_document_lines)
        found_segments.append({
            "score": segment['score'],
            "matched_lines": found_line_range
        })
    return found_segments

        
def find_clone_in_project(project_path, query, threshold=80):
    """
    Func:
        Find all similar code segments in the project
    Args:
        project_path: str, the path of the project to search in
        query: str, the code segment to search
        threshold: int, the similarity threshold
    Returns:
        found_clones: list, a list of found segments
                        {
                            "file_path": str, the file path where the code is found,
                            "score": int, the similarity score,
                            "matched_lines": list, a list of line numbers where the code is found, indexed from 0
                        }
    """
    import os
    found_clones = []
    for root, dirs, files in os.walk(project_path):
        for file in files:
            try:
                with open(os.path.join(root, file), 'r') as f:
                    document = f.read()
                
                found_segments = find_similar_code_segment(query, document, threshold)
                if found_segments != []:
                    for segment in found_segments:
                        found_clones.append({
                            "file": os.path.join(root, file),
                            "score": segment["score"],
                            "matched_lines": segment["matched_lines"]
                        })
            except:
                continue
                
    return found_clones

