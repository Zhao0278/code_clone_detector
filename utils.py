from rank_bm25 import BM25Okapi

def select_prior_edits(sliding_window, hunks):
    non_overlap_hunks = [hunk for hunk in hunks if hunk.id not in sliding_window.overlap_hunk_ids]
    choosen_hunk_ids = [hunk.id for hunk in hunks if hunk.id not in sliding_window.overlap_hunk_ids] # index to hunk id
    tokenized_corpus = ["".join(hunk.before_edit_window()+hunk.after_edit_region()).split() for hunk in non_overlap_hunks]
    bm25 = BM25Okapi(tokenized_corpus)
    tokenized_query = "".join(sliding_window.code_window).split()
    retrieval_code = bm25.get_top_n(tokenized_query, tokenized_corpus, n=3) 
    retrieved_index = [tokenized_corpus.index(i) for i in retrieval_code] # get index in choosen_hunk_ids
    prior_edit_id = [choosen_hunk_ids[idx] for idx in retrieved_index] # get corresponding hunk id
    prior_edits = [hunk for hunk in hunks if hunk.id == prior_edit_id[0]][0]
    
    return prior_edits


def label_conversion(inline_labels: list[str], inter_labels: list[str]) -> list[str]:
    """
    Func:
        Given the fine grain label of new models, convert them to old labels
    Args:   
        inline_labels: list[str], have label: keep, replace, delete
        inter_labels: list[str], have label: null, insert, block-split
    Return:
        old_labels: list[str]
    """
    assert len(inline_labels) + 1 == len(inter_labels)
    # rule 1: block-split can be ignored
    inter_labels = ["<null>" if x == "<block-split>" else x for x in inter_labels]
    
    # rule 2: delete is a part of replace
    inline_labels = ["<replace>" if x == "<delete>" else x for x in inline_labels]
    
    # rule 3: old labels can't handle insert at the beginning of code window
    inter_labels = inter_labels[1:]
    
    old_labels = []
    # rule 4: now inter_label  should only have null & insert
    #             inline_label should only have keep & replace
    for inter_label, inline_label in zip(inter_labels, inline_labels):
        if inter_label == "<null>":
            old_labels.append(inline_label)
        else: # inter_label == "insert"
            if inline_label == "<keep>":
                old_labels.append("<add>")
            else:
                old_labels.append("<replace>")
                
    assert len(old_labels) == len(inline_labels)
    return old_labels
                