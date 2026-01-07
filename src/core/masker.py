import re
from typing import List, Tuple

class Masker:
    def __init__(self):
        self.patterns = [
            r"<[^>]+>",        # Matches <TSMARKER_0>
            r"\[[^\]]+\]",     # Matches [ACTION_WEB]
            r"\{[^\}]+\}",     # Matches {player_name}
            r"%.*?[dsf]"       # Matches %s, %d
        ]

    def mask(self, text: str):
        tokens = []
        combined_pattern = f"({'|'.join(self.patterns)})"
        
        def replace_func(match):
            token = match.group(0)
            idx = len(tokens)
            tokens.append(token)
            # No spaces here! This forces the LLM to see it as part of the word
            return f"[#_{idx}_]" 
        
        masked_text = re.sub(combined_pattern, replace_func, text)
        return masked_text.strip(), tokens

    def unmask(self, masked_text: str, tokens: list):
        unmasked_text = masked_text
        for i, token in enumerate(tokens):
            # NEW: Search for the tag PLUS an accidental space
            tag_to_find = f"[#_{i}_]"
            
            # Case 1: Tag has a space after it -> "[#_0_] "
            unmasked_text = unmasked_text.replace(f"{tag_to_find} ", token)
            
            # Case 2: Tag is right against the word -> "[#_0_]Word"
            unmasked_text = unmasked_text.replace(tag_to_find, token)
            
        return unmasked_text.strip()


# Quick Test
if __name__ == "__main__":
    m = Masker()
    sample = "Hello {player_name}, you have %d gold in your <color=yellow>pouch</color>!"
    masked, tags = m.mask(sample)
    print(f"Original: {sample}")
    print(f"Masked:   {masked}")
    print(f"Tags:     {tags}")
    print(f"Restored: {m.unmask(masked, tags)}")