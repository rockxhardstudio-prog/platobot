def chunk_text(text: str, limit: int = 256) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks = []

    def split_by_separators(s: str, separators: list[str]):
        if len(s) <= limit:
            chunks.append(s)
            return

        if not separators:
            while len(s) > limit:
                chunks.append(s[:limit])
                s = s[limit:]
            if s:
                chunks.append(s)
            return

        sep = separators[0]
        parts = s.split(sep)

        current_chunk = ""
        for part in parts:
            if len(part) > limit:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                orig_chunks = chunks.copy()
                chunks.clear()
                split_by_separators(part, separators[1:])
                temp_chunks = chunks.copy()
                chunks.clear()
                chunks.extend(orig_chunks)
                chunks.extend(temp_chunks)
            elif current_chunk:
                combined = current_chunk + sep + part
                if len(combined) <= limit:
                    current_chunk = combined
                else:
                    chunks.append(current_chunk)
                    current_chunk = part
            else:
                current_chunk = part

        if current_chunk:
            chunks.append(current_chunk)

    split_by_separators(text, ["\n\n", "\n", " "])
    return chunks
