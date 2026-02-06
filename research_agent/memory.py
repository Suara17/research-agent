import os
import json
import time
import math
import hashlib
from typing import List, Optional
import unicodedata
import re

class MemoryStore:
    def __init__(self, max_short: int = 64, max_long: int = 1000, session_id: Optional[str] = None):
        self.short: List[str] = []
        self.max_short = max_short
        self.max_long = max_long
        self.session_id = session_id or f"session_{int(time.time())}"
        self.long_path = os.path.join(os.getcwd(), f"memory_store_{self.session_id}.jsonl")
        self.index = {}
        self.doc_len = {}
        self.doc_texts: List[str] = []
        self.doc_timestamps: List[int] = []
        self.doc_hashes: set = set()
        self.avgdl = 0.0
        self._jieba_available = None
        self.session_start_time = int(time.time())
        print(f"[MemoryStore] Session initialized: {self.session_id}")

    def add_short(self, item: str) -> None:
        if not item: return
        self.short.append(item)
        if len(self.short) > self.max_short:
            self.short = self.short[-self.max_short :]

    def _compute_content_hash(self, text: str) -> str:
        normalized = ''.join(text.split()).lower()
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:16]

    def _prune_old_memories(self) -> None:
        if len(self.doc_texts) <= self.max_long: return
        print(f"[MemoryStore] Pruning memories: {len(self.doc_texts)} -> {self.max_long}")
        current_time = int(time.time())
        scores = []
        for doc_id, timestamp in enumerate(self.doc_timestamps):
            age_seconds = current_time - timestamp
            age_minutes = age_seconds / 60
            if age_minutes <= 5: time_score = 1.0
            elif age_minutes <= 10: time_score = math.exp(-(age_minutes - 5) / 2.5)
            else: time_score = 0.05 * math.exp(-(age_minutes - 10) / 5)
            scores.append((doc_id, time_score))
        scores.sort(key=lambda x: x[1], reverse=True)
        keep_ids = set([doc_id for doc_id, _ in scores[:self.max_long]])
        new_texts, new_timestamps, new_hashes, new_doc_len = [], [], set(), {}
        for doc_id in sorted(keep_ids):
            new_id = len(new_texts)
            new_texts.append(self.doc_texts[doc_id])
            new_timestamps.append(self.doc_timestamps[doc_id])
            new_hashes.add(self._compute_content_hash(self.doc_texts[doc_id]))
            if doc_id in self.doc_len: new_doc_len[new_id] = self.doc_len[doc_id]
        self.doc_texts = new_texts
        self.doc_timestamps = new_timestamps
        self.doc_hashes = new_hashes
        self.doc_len = new_doc_len
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self.index = {}
        self.doc_len = {}
        self.avgdl = 0.0
        for doc_id, text in enumerate(self.doc_texts):
            self._index_doc(doc_id, text)

    def add_long(self, item: str) -> None:
        if not item or not item.strip(): return
        content_hash = self._compute_content_hash(item)
        if content_hash in self.doc_hashes: return
        try:
            timestamp = int(time.time())
            with open(self.long_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": timestamp, "text": item}, ensure_ascii=False) + "\n")
        except Exception: pass
        try:
            doc_id = len(self.doc_texts)
            self.doc_timestamps.append(timestamp)
            self.doc_hashes.add(content_hash)
            self._index_doc(doc_id, item)
            if len(self.doc_texts) > self.max_long:
                self._prune_old_memories()
        except Exception as e:
            print(f"[MemoryStore] Failed to index document: {e}")

    def _tokenize(self, text: str) -> List[str]:
        if self._jieba_available is None:
            try:
                import jieba
                self._jieba_available = True
            except ImportError:
                self._jieba_available = False
        if not self._jieba_available:
            return self._tokenize_fallback(text)
        
        import jieba
        s = unicodedata.normalize("NFKC", str(text)).lower()
        stop_cn = {"的","了","在","是","我","有","和","与","及","等","为","不","也","这","那","你","他","她","它","其","并","对","以","个","位","名","之","中","或","将","从","被","把","给","到","由","向","着","过","去","来","上","下"}
        stop_en = {"the","and","or","a","an","of","to","in","on","for","is","are","was","were","be","been","with","as","by","at","from","this","that","these","those"}
        toks = []
        try:
            for word in jieba.cut_for_search(s):
                w = word.strip()
                if not w: continue
                if w.isascii():
                    sub_words = re.findall(r"[a-z0-9]+", w)
                    for sub in sub_words:
                         if sub not in stop_en and len(sub) > 1: toks.append(sub)
                else:
                    if w not in stop_cn and len(w) > 0: toks.append(w)
            acronyms = re.findall(r'\b[A-Z]{2,}\b', text)
            toks.extend([a.lower() for a in acronyms if a.lower() not in stop_en])
            camel_case = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', text)
            toks.extend([c.lower() for c in camel_case])
            return toks
        except Exception:
            return self._tokenize_fallback(text)

    def _tokenize_fallback(self, text: str) -> List[str]:
        try:
            s = unicodedata.normalize("NFKC", str(text)).lower()
            stop_en = {"the","and","or","a","an","of","to","in","on","for","is","are","was","were","be","been","with","as","by","at","from","this","that","these","those"}
            stop_cn = {"的","了","在","是","我","有","和","与","及","等","为","不","也","这","那","你","他","她","它","其","并","对","以","将","从","被","把","给"}
            toks = []
            words = re.findall(r"[A-Za-z0-9]+", s)
            for w in words:
                if w in stop_en: continue
                toks.append(w)
                if len(w) > 4:
                    for i in range(len(w) - 1): toks.append(w[i : i + 2])
                    if len(w) > 6:
                        for i in range(len(w) - 2): toks.append(w[i : i + 3])
            seqs = re.findall(r"[\u4e00-\u9fff]+", s)
            for seq in seqs:
                cands = [seq, re.sub(r"(集团公司|集团|有限公司|股份有限公司|公司|大学|学院|学校|电视台|报社|出版社|研究院|研究所|中心|基金会)$", "", seq)]
                seen = set()
                for cand in cands:
                    if not cand or cand in seen: continue
                    seen.add(cand)
                    for ch in cand:
                        if ch not in stop_cn: toks.append(ch)
                    if len(cand) >= 2:
                        for i in range(len(cand) - 1): toks.append(cand[i : i + 2])
                    if len(cand) >= 4:
                        for i in range(len(cand) - 2): toks.append(cand[i : i + 3])
            numbers = re.findall(r'\b\d{4}\b', text)
            toks.extend(numbers)
            return toks
        except Exception:
            return []

    def _index_doc(self, doc_id: int, text: str) -> None:
        from collections import Counter
        toks = self._tokenize(text)
        tf = Counter(toks)
        self.doc_len[doc_id] = sum(tf.values())
        self.doc_texts.append(text)
        for term, cnt in tf.items():
            posting = self.index.get(term)
            if posting is None:
                posting = {}
                self.index[term] = posting
            posting[doc_id] = cnt
        n = len(self.doc_texts)
        if n: self.avgdl = sum(self.doc_len.values()) / float(n)

    def build_index(self) -> None:
        self.index = {}
        self.doc_len = {}
        self.doc_texts = []
        self.doc_timestamps = []
        self.doc_hashes = set()
        self.avgdl = 0.0
        if not os.path.exists(self.long_path): return
        try:
            with open(self.long_path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s: continue
                    try:
                        j = json.loads(s)
                        text = str(j.get("text") or "")
                        timestamp = j.get("t", int(time.time()))
                        if not text: continue
                        content_hash = self._compute_content_hash(text)
                        if content_hash in self.doc_hashes: continue
                        doc_id = len(self.doc_texts)
                        self.doc_timestamps.append(timestamp)
                        self.doc_hashes.add(content_hash)
                        self._index_doc(doc_id, text)
                    except Exception: continue
            if len(self.doc_texts) > self.max_long:
                self._prune_old_memories()
        except Exception as e:
            print(f"[MemoryStore] Failed to build index: {e}")

    def _df(self, term: str) -> int:
        posting = self.index.get(term)
        return len(posting) if posting else 0

    def search_and_inject(self, query: str, top_k: int = 3) -> List[dict]:
        results = self.search(query, top_k=top_k, time_boost=True)
        current_time = int(time.time())
        enriched = []
        for r in results:
            try:
                doc_id = self.doc_texts.index(r["text"])
                age_days = (current_time - self.doc_timestamps[doc_id]) / 86400
                enriched.append({"text": r["text"], "score": r["score"], "age_days": int(age_days)})
            except (ValueError, IndexError):
                enriched.append({"text": r["text"], "score": r["score"], "age_days": 0})
        return enriched

    def search(self, query: str, top_k: int = 3, time_boost: bool = True) -> List[dict]:
        k1 = 1.5
        b = 0.75
        if any("\u4e00" <= ch <= "\u9fff" for ch in str(query)):
            k1 = 1.2
            b = 0.6
        toks = self._tokenize(query)
        N = len(self.doc_texts)
        if N == 0 or not toks: return []
        scores = {}
        for t in set(toks):
            posting = self.index.get(t)
            df = self._df(t)
            if not posting or df == 0: continue
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
            for doc_id, tf in posting.items():
                dl = self.doc_len.get(doc_id, 0)
                denom = tf + k1 * (1 - b + b * (dl / (self.avgdl or 1.0)))
                s = idf * (tf * (k1 + 1) / (denom or 1.0))
                scores[doc_id] = scores.get(doc_id, 0.0) + s
        
        phrase = unicodedata.normalize("NFKC", str(query)).strip()
        if phrase:
            for doc_id in list(scores.keys()):
                try:
                    c = self.doc_texts[doc_id].count(phrase)
                    if c > 0: scores[doc_id] += 0.3 * float(c)
                except Exception: pass
        
        try:
            s = unicodedata.normalize("NFKC", str(query)).lower()
            seqs = re.findall(r"[\u4e00-\u9fff]+", s)
            bigrams, trigrams = [], []
            for seq in seqs:
                if len(seq) >= 2:
                    for i in range(len(seq) - 1): bigrams.append(seq[i : i + 2])
                if len(seq) >= 3:
                    for i in range(len(seq) - 2): trigrams.append(seq[i : i + 3])
            for doc_id in list(scores.keys()):
                text = self.doc_texts[doc_id]
                bc = sum(text.count(bg) for bg in bigrams)
                tc = sum(text.count(tg) for tg in trigrams)
                if bc > 0: scores[doc_id] += 0.15 * float(bc)
                if tc > 0: scores[doc_id] += 0.25 * float(tc)
        except Exception: pass

        qset = set(toks)
        for doc_id in list(scores.keys()):
            matched = 0
            for t in qset:
                posting = self.index.get(t)
                if posting and doc_id in posting: matched += 1
            if len(qset) > 0:
                cov = matched / float(len(qset))
                scores[doc_id] *= (1.0 + 0.2 * cov)

        if time_boost and self.doc_timestamps:
            current_time = int(time.time())
            for doc_id in list(scores.keys()):
                if doc_id < len(self.doc_timestamps):
                    age_seconds = current_time - self.doc_timestamps[doc_id]
                    age_minutes = age_seconds / 60
                    if age_minutes <= 2: time_factor = 1.5
                    elif age_minutes <= 5: time_factor = 1.2
                    elif age_minutes <= 10: time_factor = 1.0
                    else: time_factor = 0.5
                    scores[doc_id] *= time_factor

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max(1, int(top_k))]
        return [{"text": self.doc_texts[d], "score": float(sc)} for d, sc in ranked]
