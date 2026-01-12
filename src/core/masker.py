import re
from typing import List, Tuple

from core.tag_utils import extract_tags

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
            # Use @@ format - doesn't match any of our patterns and is visible to AI
            return f"@@PLACEHOLDER_{idx}@@" 
        
        masked_text = re.sub(combined_pattern, replace_func, text)
        return masked_text.strip(), tokens

    def unmask(self, masked_text: str, tokens: list):
        unmasked_text = masked_text
        for i, token in enumerate(tokens):
            # Try exact match first
            placeholder = f"@@PLACEHOLDER_{i}@@"
            if placeholder in unmasked_text:
                unmasked_text = unmasked_text.replace(placeholder, token)
            else:
                # Try with optional spaces (in case AI added them)
                pattern = r"@@\s*PLACEHOLDER_" + str(i) + r"\s*@@"
                unmasked_text = re.sub(pattern, token, unmasked_text)
            
        return unmasked_text.strip()
    
    def get_tag_skeleton(self, text: str) -> str:
        """Extracts only the tags from the text and returns them joined with a space."""
        return " ".join(extract_tags(text))


# Dev-only smoke test (not user-visible in production).
if __name__ == "__main__":
    m = Masker()
    sample = "Hello {player_name}, you have %d gold in your <color=yellow>pouch</color>!"
    masked, tags = m.mask(sample)
    print(f"Original: {sample}")
    print(f"Masked:   {masked}")
    print(f"Tags:     {tags}")
    restored = m.unmask(masked, tags)
    print(f"Restored: {restored}")
    assert restored == sample
    print("Smoke test passed!")
