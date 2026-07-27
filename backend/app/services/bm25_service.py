from rank_bm25 import BM25Okapi
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="jieba")
import jieba

import os
import logging
from typing import List, Dict, Tuple, Any

# Suppress jieba DEBUG logs
logging.getLogger('jieba').setLevel(logging.WARNING)

# 設定字典路徑 (僅保留基礎大詞典)
DICT_PATH = os.path.join(os.path.dirname(__file__), "dictionaries", "dict.txt.big")

if os.path.exists(DICT_PATH):
    jieba.set_dictionary(DICT_PATH)

class BM25Service:
    def __init__(self):
        self._corpus = []
        self._bm25 = None
        self._chunk_map = {} # map chunk_id to chunk data
        
    def add_terms(self, terms: List[str]) -> None:
        """
        動態加入術語到 Jieba 分詞詞典
        避免專有名詞（如 KP 名稱）被切分過細
        """
        for term in terms:
            if term and term.strip():
                jieba.add_word(term.strip())
        # logger.debug(f"BM25Service: Added {len(terms)} terms to dynamic dictionary.")

    def build_index(self, chunks: List[Dict[str, Any]]) -> None:
        """
        建立 BM25 索引
        
        Args:
            chunks: [{"chunk_id": 1, "text": "..."}, ...]
        """
        self._corpus = []
        self._chunk_map = {}
        tokenized_corpus = []
        
        for chunk in chunks:
            chunk_text = chunk.get("text", "")
            if not chunk_text:
                continue
                
            # 中文分詞 (繁體) - 使用搜索引擎模式
            # cut_for_search 會對長詞再次切分，適合關鍵字搜索
            tokens = list(jieba.cut_for_search(chunk_text))
            
            # 移除空白、標點與停用詞
            stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一個', '上', '也', '很', '到', '說', '要', '去', '你', '會', '著', '沒有', '看', '好', '自己', '這'}
            tokens = [t for t in tokens if t.strip() and t not in stopwords and len(t) > 1]
            
            self._corpus.append({
                "chunk_id": chunk["chunk_id"],
                "tokens": tokens
            })
            self._chunk_map[chunk["chunk_id"]] = chunk
            tokenized_corpus.append(tokens)
        
        if tokenized_corpus:
            self._bm25 = BM25Okapi(tokenized_corpus)
        else:
            self._bm25 = None
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        BM25 搜尋
        
        Returns:
            [(chunk_id, bm25_score), ...]
        """
        if not self._bm25:
            # logger.warning("BM25Service: No index built")
            return []
            
        # 使用搜索引擎模式進行分詞
        query_tokens = list(jieba.cut_for_search(query))
        stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一個', '上', '也', '很', '到', '說', '要', '去', '你', '會', '著', '沒有', '看', '好', '自己', '這'}
        query_tokens = [t for t in query_tokens if t.strip() and t not in stopwords and len(t) > 1]
        
        # Suppressed BM25 search debug prints
        pass
        
        scores = self._bm25.get_scores(query_tokens)
        
        # 排序並返回 top_k
        # scores 對應 self._corpus 的 index
        ranked_results = []
        for i, score in enumerate(scores):
            if score > 0: # 只返回有關聯的
                entry = self._corpus[i]
                ranked_results.append((entry["chunk_id"], float(score)))
                
        # Sort by score desc
        ranked_results.sort(key=lambda x: x[1], reverse=True)
        
        top_results = ranked_results[:top_k]
        
        # Suppressed BM25 search result prints
        pass
        
        return top_results
