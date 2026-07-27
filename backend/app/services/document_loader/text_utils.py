"""
PDF 文字合併工具：智能處理換行斷句問題

問題：
PDF 的 extract_text_lines() 會逐行提取，導致句子被斷開：
"Building Intelligent AI
Agents: A Complete
Architecture Guide with
Code"

解決方案：
1. 檢測行尾是否完整（有標點、全大寫、數字等）
2. 如果不完整，與下一行合併
3. 保留刻意的換行（列表、標題等）
"""
import re


def is_noise_line(text: str) -> bool:
    """判定一行是否為純噪音（如 ‹#›、單行頁碼、PPT站位符）"""
    stripped = text.strip()
    if not stripped:
        return True
        
    # 1. 移除 ‹#› 或 <#> (常見於 PowerPoint 轉 PDF)
    if re.match(r'^[‹<]#+[›>]$', stripped):
        return True
        
    # 2. 移除單行頁碼 (1-3 位數字, 或 Page 1, P.1, 1/10, Slide 3, - 3 -)
    # 支援帶點格式 (3., 12.) 及更多的包裹符號
    # 以及處理 "Slide 3" 這種常見 PPT 格式
    page_pattern = r'^([(\[-]?\s*(\d{1,3}\.?|[Pp]age\s+\d+|[Pp]\.\s*\d+|[Ss]lide\s+\d+|\d+\s*/\s*\d+)\s*[)\]-]?)$'
    if re.match(page_pattern, stripped):
        return True
        
    return False


def smart_merge_lines(lines: list[str]) -> str:
    """
    智能合併 PDF 提取的行，處理因排版導致的斷句
    
    規則：
    1. 程式碼段落：保留原始格式，用 [code]...[/code] 包裹
    2. 行尾有句號、問號、驚嘆號、冒號 → 保留換行
    3. 行尾是完整單詞（大寫、數字、括號） → 保留換行
    4. 空行 → 保留（段落分隔）
    5. 其他情況 → 與下一行合併（用空格）
    
    Args:
        lines: List of text lines from PDF
        
    Returns:
        Merged text string with code blocks preserved
    """
    if not lines:
        return ""
    
    # 0. 預處理：清除標籤並過濾噪音行
    cleaned = []
    for line in lines:
        # 1. 清除 [code] 標籤
        l = re.sub(r'\[/?code\]', '', line, flags=re.IGNORECASE)
        
        # 2. 清除 ‹#› 或 <#> (可能出現在行內或單獨一行)
        l = re.sub(r'[‹<]#+[›>]', '', l)
        
        # 3. 固定錯位括號
        l = _fix_displaced_parentheses(l)
        
        # 4. 噪音行過濾
        if is_noise_line(l):
            continue
            
        cleaned.append(l)
    lines = cleaned
    
    # 第一步：檢測程式碼區塊
    segments = _segment_code_and_text(lines)
    
    # 3. 根據類型重新組裝
    merged_parts = []
    for type, seg_lines in segments:
        if type == "code":
            # 清理可能存在的舊標籤（再次清理以防萬一），避免重複包裹
            clean_lines = [re.sub(r'\[/?[Cc]ode\]', '', l) for l in seg_lines]
            content = "\n".join(clean_lines).strip('\n')
            if content.strip():  # 只添加非空代碼塊（檢查是否只有空白）
                merged_parts.append(f"[code]\n{content}\n[/code]")
        else:
            merged_text = _merge_text_lines(seg_lines)
            
            # [NEW] 優化空格：移除多餘空格，處理中英文間距
            # 1. 將多個連續空格縮減為一個
            merged_text = re.sub(r'[ \t]+', ' ', merged_text)
            
            # 2. 移除中文字之間的多餘空格 (例如: "資 料 前 處 理" -> "資料前處理")
            # 查找：中文字 [空格] 中文字
            merged_text = re.sub(r'([\u4e00-\u9fa5])\s+([\u4e00-\u9fa5])', r'\1\2', merged_text)
            
            # 3. 移除中文與標點之間的空格 (例如: "資料 ，" -> "資料，")
            merged_text = re.sub(r'([\u4e00-\u9fa5])\s+([，。！？：；、])', r'\1\2', merged_text)
            merged_text = re.sub(r'([，。！？：；、])\s+([\u4e00-\u9fa5])', r'\1\2', merged_text)
            
            merged_parts.append(merged_text)
            
    return "\n\n".join(merged_parts)


def _segment_code_and_text(lines: list[str]) -> list[tuple[str, list[str]]]:
    """
    將文本分割成程式碼段落和普通文字段落
    改進：合併距離接近的程式碼段落（避免過度分割）
    """
    current_type = None
    current_lines = []
    
    # 第一輪：基本分割
    raw_segments = []
    for i, line in enumerate(lines):
        is_code = _is_code_line(line, i, lines)
        
        if current_type is not None and is_code != (current_type == "code"):
            if current_lines:
                raw_segments.append((current_type, current_lines))
            current_lines = [line]
            current_type = "code" if is_code else "text"
        else:
            if current_type is None:
                current_type = "code" if is_code else "text"
            current_lines.append(line)
    
    # 最後一段
    if current_lines:
        raw_segments.append((current_type, current_lines))
    
    # 第二輪：合併相鄰的程式碼段落（更激進的策略）
    # 如果兩個程式碼段落之間只有很少文字（<= 5行）或空行，合併它們
    segments = []
    i = 0
    while i < len(raw_segments):
        seg_type, seg_lines = raw_segments[i]
        
        # 如果當前是程式碼段落，嘗試向後合併
        if seg_type == "code":
            merged_lines = seg_lines.copy()
            j = i + 1
            
            # 持續向後檢查
            while j < len(raw_segments):
                next_seg_type, next_seg_lines = raw_segments[j]
                
                if next_seg_type == "code":
                    # 直接合併下一個程式碼段落
                    merged_lines.extend(next_seg_lines)
                    j += 1
                elif next_seg_type == "text":
                    # 檢查文字段落的長度和內容
                    text_content = '\n'.join(next_seg_lines).strip()
                    
                    # 判斷這段文字是否其實應該是程式碼的一部分
                    # 1. 如果是駐解（# 或 // 開頭）
                    # 2. 如果是很短的賦值語句（e.g. x = 1）
                    # 3. 如果是空行或很短的過渡文字（<= 3行），且不像是完整的英文句子
                    
                    is_comment = any(line.strip().startswith(('#', '//', '/*', '*')) for line in next_seg_lines)
                    is_short_assignment = len(next_seg_lines) <= 2 and all('=' in line for line in next_seg_lines)
                    
                    # 嚴格的連接詞檢查：不能像是完整的句子（大寫開頭，標點結尾）
                    # 嚴格的連接詞檢查：不能像是完整的句子（大寫開頭，標點結尾，或包含中文標點）
                    is_sentence_en = bool(re.match(r'^[A-Z].*[\.!?:;]$', text_content, re.DOTALL))
                    is_sentence_cn = bool(re.search(r'[\u4e00-\u9fa5]', text_content) and re.search(r'[。！？：，、]', text_content))
                    is_sentence = is_sentence_en or is_sentence_cn
                    is_connector = (len(next_seg_lines) <= 3 or not text_content) and not is_sentence
                    
                    # [Fix] 檢查是否為代碼延續行（上一行以符號結尾，這一段是後續）
                    # 例如上一行結束於 '->' 或 '(' 或 '[' 或 '{' 或 ','
                    is_continuation = False
                    if merged_lines:
                        # Find last non-empty line
                        for k in range(len(merged_lines) - 1, -1, -1):
                            if merged_lines[k].strip():
                                last_line = merged_lines[k].strip()
                                if last_line.endswith(('->', '(', '[', '{', ',')):
                                    is_continuation = True
                                break
                            
                    # 如果後面還有程式碼，或者這段文字本身就像程式碼（註解/賦值），或者它是代碼延續
                    has_following_code = j + 1 < len(raw_segments) and raw_segments[j + 1][0] == "code"
                    
                    # [Fix] 如果是強制的代碼延續（例如 List[Dict]: 或 closing bracket），不需要 has_following_code 也可以合併
                    is_valid_continuation = False
                    
                    # 檢查是否以符號開頭或結尾，或者是類型標註
                    is_type_hint = bool(re.search(r'^[A-Z]\w+(\[.*\])?:?$', text_content))
                    is_closing = text_content.strip().startswith((')', ']', '}'))
                    is_chained_call = text_content.strip().startswith('.')
                    # 字典內容：'key': value
                    is_dict_item = bool(re.search(r'^[\'"]\w+[\'"]\s*:', text_content))
                    # Docstring start
                    is_docstring = text_content.strip().startswith(('"""', "'''"))
                    
                    if is_continuation and (is_type_hint or is_closing or is_chained_call or is_dict_item or is_docstring):
                         is_valid_continuation = True
                    elif is_closing or is_docstring: # closing brackets/docstrings are strong signals
                         is_valid_continuation = True

                    if (has_following_code and (is_connector or is_comment or is_short_assignment or is_continuation)) or is_valid_continuation:
                        merged_lines.extend(next_seg_lines)
                        j += 1
                        continue
                    
                    # 如果後面沒有程式碼了，但這段文字緊接著程式碼且是註解，也合併進來（避免結尾註解被切斷）
                    if not has_following_code and is_comment:
                        merged_lines.extend(next_seg_lines)
                        j += 1
                        continue
                        
                    # [Fix] 如果這是代碼延續（例如 List[Dict]:），即使後面沒有代碼，也應該合併進來
                    if not has_following_code and is_continuation:
                         # 再次檢查這段內容是否真的像是代碼的一部分
                         # 檢查是否以符號開頭或結尾，或者是類型標註
                         is_type_hint = bool(re.search(r'^[A-Z]\w+(\[.*\])?:?$', text_content))
                         is_closing = text_content.strip().startswith((')', ']', '}'))
                         
                         if is_type_hint or is_closing:
                            merged_lines.extend(next_seg_lines)
                            j += 1
                            continue

                    # 否則停止合併
                    break
                else:
                    break
            
            # 檢查前一個段落是否為註解，如果是則合併進來（處理 Leading Comments）
            if segments and segments[-1][0] == "text":
                prev_lines = segments[-1][1]
                # 檢查最後一個段落是否全是註解
                is_prev_comment = all(line.strip().startswith(('#', '//', '/*', '*')) for line in prev_lines if line.strip())
                # [Fix] 檢查是否為 Decorator (@開頭)
                is_decorator = all(line.strip().startswith('@') for line in prev_lines if line.strip())
                
                if is_prev_comment or is_decorator:
                    # 將前一段是註解或裝飾器的內容合併到當前代碼塊的最前面
                    merged_lines = prev_lines + merged_lines
                    # 移除已添加的最後一段
                    segments.pop()

            segments.append(("code", merged_lines))
            i = j
        else:
            # 普通文字段落，直接加入
            segments.append((seg_type, seg_lines))
            i += 1
    
    return segments


def _is_code_line(line: str, index: int, all_lines: list[str]) -> bool:
    """
    判斷一行是否為程式碼（保守策略）
    """
    stripped = line.strip()
    
    # 規則 0: 空行處理
    # 如果是空行，檢查上下文是否為代碼
    if not stripped:
        if index > 0 and index < len(all_lines) - 1:
            prev_line = all_lines[index - 1]
            next_line = all_lines[index + 1]
            prev_score = _calculate_code_score(prev_line) if prev_line.strip() else 0
            next_score = _calculate_code_score(next_line) if next_line.strip() else 0
            
            # 只有當前後都是明確的代碼時，空行才算代碼
            return prev_score >= 1.5 and next_score >= 1.5
        return False
    
    # 規則 1: [NEW] 強制排除列表項目 (Bullet points) - 優先級最高
    # 必須放在縮排檢查之前，因為列表項目通常也有縮排
    # 支援: •, -, *, 1., 1), (1), a., a), (a)
    if re.match(r'^([•●○▪▫\-\*]|\d+[\.\)]|[a-zA-Z][\.\)]|\(\w+\))\s+', stripped):
        return False

    # 規則 2: [NEW] 強制排除一般文字句子 (包含了 英文 + 中文)
    # 特徵: 包含文字標點，且不包含明顯的程式語法符號
    
    # 常見句子結尾 (英/中)
    has_sentence_end = bool(re.search(r'[\.!?:;。！？]$', stripped))
    # 常見文字分隔符 (英/中)
    has_text_separators = bool(re.search(r'[,，、]', stripped))
    # 是否包含程式碼專有符號 (需避開一般括號)
    has_code_symbols = bool(re.search(r'[{}=;\[\]]|\->|=>|\+=|\-=|\*=|&&|\|\|', stripped))
    # 是否包含中文字
    has_chinese = bool(re.search(r'[\u4e00-\u9fa5]', stripped))
    
    # [NEW] 標題檢查: 如果是 Title Case (Data Cleaning) 且沒有代碼符號 -> False
    # 允許空白, 字母, 數字, 括號 (Data Cleaning (Vol. 1))
    is_title_case = bool(re.match(r'^[A-Z][a-zA-Z0-9\s\(\)\-]+$', stripped))
    
    # [NEW] 純數字檢查: 頁碼, 年份, "10.", "8" -> False
    is_number_like = bool(re.match(r'^\d+[\.]?$', stripped))

    # [NEW] Email 檢查: 只包含 Email
    is_email = bool(re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', stripped))

    # [NEW] 電話號碼檢查: (02)2732-1104 #55337
    # 允許: 數字, -, (, ), #, 空格. 且長度至少 6
    # 為了避免誤判數學算式 (1-2), 限制必須包含至少一個特定電話格式符號或足夠長
    is_phone = bool(re.match(r'^[\d\-\(\)\s#]+$', stripped)) and len(stripped) > 6 and re.search(r'[\(\)#]', stripped)

    # 如果像是句子、標題、數字、Email 或電話，且沒有強烈的程式碼符號 -> False
    if (has_sentence_end or has_text_separators or has_chinese or is_title_case or is_number_like or is_email or is_phone) and not has_code_symbols:
        # 排除例外：print("中文") 這種代碼
        # 簡單檢查: 如果行首是常見的代碼關鍵字，則不排除
        if not re.match(r'^(print|console\.log|logger|logging|return|raise|yield)\b', stripped):
            return False

    # 規則 3: 縮排 (Indentation)
    # 縮排是代碼的強烈信號，但如果它看起來完全像文字 (在規則2已經處理)，就不應該只因為縮排就當作代碼
    # 這裡保留縮排規則，但已經過濾掉了大部分的誤判
    if line.startswith('  ') or line.startswith('\t'):
        return True

    # 規則 4: 明顯的代碼特徵 (Keywords, Imports, etc.)
    
    # Import 語句
    if stripped.startswith('import ') or stripped.startswith('from '):
        if re.search(r'^(import\s+|from\s+\S+(?:\.\S+)*\s+import\s+)', stripped):
            return True
            
    # Decorator (@開頭)
    if stripped.startswith('@'):
        return True
    
    # 明顯的變數存取/賦值 (e.g., var['key'].func())
    if re.match(r'^[\w\.]+(\[\'[\w]+\'\]|\["\w+"\])+', stripped):
        return True
    
    # 物件.屬性 check (e.g. step.requires_tool:)
    if re.match(r'^[\w\.]+\.\w+:', stripped):
        return True

    # Docstring start/end
    if stripped.startswith(('"""', "'''")):
        return True

    # 規則 5: 程式語法特徵評分
    code_score = _calculate_code_score(stripped)
    return code_score >= 2.0


def _calculate_code_score(line: str) -> float:
    """計算程式碼信號強度（0-5），分數越高越可能是程式碼"""
    score = 0.0
    
    # [Fix] 將關鍵字分為兩類：必須在行首 vs 可以在任何位置
    # 類別 1: 行首關鍵字 (避免 "foundation for" 被誤判)
    start_keywords = [
        r'\bdef\b', r'\bclass\b', 
        r'\breturn\b', r'\bif\b', r'\belse\b', r'\bfor\b', r'\bwhile\b', 
        r'\btry\b', r'\bexcept\b', r'\bwith\b', r'\braise\b'
    ]
    
    # 類別 2: 可以在任何位置的強關鍵字
    inline_keywords = [
        r'\basync\b', r'\bawait\b', r'\bconst\b', r'\blet\b', r'\bvar\b',
        r'\bpublic\b', r'\bprivate\b', r'\bprotected\b', r'\bstatic\b',
        r'\bprint\b', r'\bconsole\.log\b', r'\bpass\b', r'\bcontinue\b', r'\bbreak\b',
        r'\blambda\b'
    ]
    
    for pattern in start_keywords:
        # 檢查是否在行首 (允許前面的標點如 (, [, { 等，如果是 comprehension)
        if re.match(r'^[^a-zA-Z0-9]*' + pattern, line):
            score += 2
            break
            
    for pattern in inline_keywords:
        if re.search(pattern, line):
            score += 2
            break
            
    if re.search(r'\bfunction\s*[\w(]', line):
        score += 2

    # Import
    if re.search(r'^\s*from\s+[\w.]+\s+import\b', line) or re.search(r'^\s*import\s+[\w.]+', line):
        score += 2
    
    # 賦值
    if '=' in line and ':' not in line:
        if re.match(r'^\s*[\w\.]+\s*=\s*.+', line):
            score += 1.5
            if len(line) < 40:
                score += 0.5
    
    # 函數調用
    if re.search(r'^\s*[\w\.]+\([^)]*\)', line):
        score += 1.5 
    elif re.search(r'[\w\.]+\([^)]*\)', line):
        score += 1
    
    # 行尾符號
    # [Fix] Add operators to line ending signal 
    if line.rstrip().endswith((':', ';', '{', '}', '[', ']', '(', ')', '->', ',', '+', '-', '*', '/')):
        score += 1.0 
    
    # 特殊運算符
    special_patterns = ['->', '=>', '::', '&&', '||', '!=', '==', '+=', '-=', '*=', '/=']
    if any(pattern in line for pattern in special_patterns):
        score += 1
        
    return score


def _merge_text_lines(lines: list[str]) -> str:
    """
    合併普通文字行（原有的邏輯）
    """
    merged = []
    buffer = ""
    
    for i, line in enumerate(lines):
        line = line.rstrip()
        
        # 空行：刷新緩衝區，保留段落分隔
        if not line.strip():
            if buffer:
                merged.append(buffer)
                buffer = ""
            continue  # 不保留空行（段落用 \n\n 分隔）
        
        # 添加到緩衝區
        if buffer:
            buffer += " " + line
        else:
            buffer = line
        
        # 檢查是否應該保留換行
        should_break = _should_break_line(buffer, i, lines)
        
        if should_break:
            merged.append(buffer)
            buffer = ""
    
    # 處理最後的緩衝區
    if buffer:
        merged.append(buffer)
    
    return "\n".join(merged)


def _should_break_line(line: str, index: int, all_lines: list[str]) -> bool:
    """
    判斷當前行是否應該換行
    
    Returns:
        True: 應該換行
        False: 應該與下一行合併
    """
    if not line:
        return True
    
    # 最後一行
    if index >= len(all_lines) - 1:
        return True
    
    # 規則 1: 行尾有終止標點
    if line.rstrip()[-1] in ".!?。！？:：":
        return True
    
    # 規則 2: 行尾是數字（可能是編號列表）
    if line.rstrip()[-1].isdigit():
        return True
    
    # 規則 3: 整行都是大寫（可能是標題）
    if line.strip().isupper() and len(line.strip()) < 100:
        return True
    
    # 規則 4: 下一行開頭是列表標記
    next_line = all_lines[index + 1].strip() if index + 1 < len(all_lines) else ""

    # 規則 4: 下一行開頭是列表標記 (Bullet points)
    if next_line and next_line[0] in "•●○▪▫-*":
        return True
    
    # 規則 5: 中文標題偵測 (Heuristic)
    # 如果一行很短 (少於 20 個字) 且不含標點符號，且下一行字數顯著增加，則視為標題
    if re.search(r'[\u4e00-\u9fa5]', line):
        clean_line = line.strip()
        # 不包含常見的句子連接或結尾標點
        if len(clean_line) < 20 and not re.search(r'[,，、;；:：]', clean_line):
            return True

    # 規則 6: 下一行開頭是數字+點（編號列表）
    if re.match(r'^\d+[\.)]\s', next_line):
        return True
    
    # 規則 7: 如果當前行以連字符結尾，通常表示單詞被斷開，不應換行
    if line.rstrip().endswith('-'):
        return False
    
    # 默認：合併到下一行
    return False



def _fix_displaced_parentheses(line: str) -> str:
    """
    修復 PDF 提取時錯位的括號內容。
    例如： "資料清洗 ( ) 去除重複資料       Data Cleaning"
    轉換為： "資料清洗 (Data Cleaning) 去除重複資料"
    
    Updated: 支持後面還有其他文字的情況
    例如： "資料清洗 ( )      Data Cleaning 這一步驟..."
    """
    # 模式：
    # 1. 前段文字 (prefix)
    # 2. 空括號 ( ) 或 （ ）
    # 3. 中段文字 (middle) - 括號和填充詞之間的內容
    # 4. 分隔符 (gap) - 至少2個空白
    # 5. 填充內容 (filling) - 英文、數字、冒號
    # 6. 後續文字 (suffix) - 接在填充詞後面的內容 (可能是中文)
    
    # 使用 Lookahead 確保填充內容停在中文或行尾之前
    # (\s{2,}) 捕獲 Gap
    # ([a-zA-Z0-9\s:_\-]+?) 捕獲 English (非貪婪)，直到遇到...
    # (?=\s*[\u4e00-\u9fa5]|$) ...中文或行尾
    
    pattern = r'^(.*?)([\(（]\s*[\)）])(.*?)(\s{2,})([a-zA-Z0-9\s:_\-]+?)\s*(?=\s+[\u4e00-\u9fa5]|$)(.*)$'
    
    match = re.search(pattern, line)
    if match:
        prefix = match.group(1)
        # parens = match.group(2) 
        middle = match.group(3)
        # gap = match.group(4)
        filling = match.group(5).strip()
        # [Fix] suffix 之前可能有多餘的空白，需要 strip 或保留一個空格
        suffix = match.group(6) 
        
        # 簡單驗證：如果 filling 太長（超過50字），可能不是括號內容，而是另一欄文字
        if len(filling) > 50:
            return line
            
        # 移除 filling 尾部的冒號（如果是 Data Cleaning : 這種標題格式）
        # 通常括號內不需要冒號
        clean_filling = filling.rstrip(' :')
        
        # 構造新字串
        # 使用半形括號
        # 如果 suffix 存在且開頭是中文字，補一個空格保持美觀
        # 如果 suffix 是空字串或標點，則不需要
        
        reconstructed = f"{prefix}({clean_filling}){middle}"
        
        if suffix:
            # 去除 suffix 開頭多餘空白
            clean_suffix = suffix.lstrip()
            # 如果 middle 結尾沒有空白，且 suffix 是中文或英文，補一個空白
            if not middle.endswith(' ') and clean_suffix:
                reconstructed += " " + clean_suffix
            else:
                reconstructed += clean_suffix
        
        return reconstructed.strip()
        
    return line


# 測試案例
if __name__ == "__main__":
    test_lines = [
        "Building Intelligent AI",
        "Agents: A Complete",
        "Architecture Guide with",
        "Code",
        "",
        "This is a normal paragraph that should",
        "be merged into one line without breaking",
        "the sentence flow.",
        "",
        "Here is some example code:",
        "",
        "    def smart_merge_lines(lines):",
        "        if not lines:",
        "            return ''",
        "        result = []",
        "        for line in lines:",
        "            result.append(line)",
        "        return '\\n'.join(result)",
        "",
        "The function above demonstrates",
        "how to process text lines.",
        "",
        "• Bullet point one",
        "• Bullet point two",
        "",
        "1. Numbered item",
        "2. Another item"
    ]
    
    result = smart_merge_lines(test_lines)
    print(result)
    print("\n" + "="*50)
    print("Expected: Title merged, paragraph merged, code preserved, bullets preserved")
