import os
from tqdm import tqdm
from transformers import MarianMTModel, MarianTokenizer
import torch


class LocalTranslator:
    def __init__(self, device=None):
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        
        self.models = {}
        self.tokenizers = {}
        print(f"Translator initialized using device: {self.device}")
    
    # Load appropriate MarianMT model for language pair
    def load_model(self, source_lang, target_lang):
        model_name = self._get_model_name(source_lang, target_lang)
        
        if model_name not in self.models:
            print(f"\nLoading translation model: {model_name}")
            try:
                tokenizer = MarianTokenizer.from_pretrained(model_name)
                model = MarianMTModel.from_pretrained(model_name).to(self.device)
                
                self.models[model_name] = model
                self.tokenizers[model_name] = tokenizer
                print(f"Model loaded successfully")
            except Exception as e:
                raise Exception(f"Error loading model {model_name}: {str(e)}")
                
        return self.models[model_name], self.tokenizers[model_name]
    
    # Get the appropriate model name for the language pair
    def _get_model_name(self, source_lang, target_lang):
        # Language code mapping
        lang_codes = {
            'en': 'en',
            'he': 'heb',
            'es': 'es',
            'fr': 'fr',
            'de': 'de',
            'ru': 'ru',
            'it': 'it',
            'ar': 'ar',
            'zh': 'zh',
            'ja': 'jap',
            'ko': 'kor',
        }
        
        source = lang_codes.get(source_lang, source_lang)
        target = lang_codes.get(target_lang, target_lang)
        
        # Special cases for Hebrew and other non-standard pairs
        if target_lang == 'he':
            if source_lang == 'en':
                return "Helsinki-NLP/opus-mt-en-he"
            # For other sources to Hebrew, we'll translate through English
            return None
        
        # Standard Helsinki NLP model naming
        return f"Helsinki-NLP/opus-mt-{source}-{target}"
    
    def translate_text(self, text, source_lang, target_lang, max_length=512):
        if not text.strip():
            return text
        
        try:
            model_name = self._get_model_name(source_lang, target_lang)
            
            # If no direct translation available, go through English
            if model_name is None:
                # First translate to English
                english_text = self.translate_text(text, source_lang, 'en', max_length)
                # Then translate from English to target
                return self.translate_text(english_text, 'en', target_lang, max_length)
            
            model, tokenizer = self.load_model(source_lang, target_lang)
            
            # Split long text into sentences
            sentences = text.split('. ')
            translated_parts = []
            
            for sentence in sentences:
                if not sentence.strip():
                    continue
                    
                # Tokenize and translate
                inputs = tokenizer(sentence, return_tensors="pt", max_length=max_length, truncation=True)
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                
                with torch.no_grad():
                    translated = model.generate(**inputs, max_length=max_length)
                    decoded = tokenizer.batch_decode(translated, skip_special_tokens=True)[0]
                    
                translated_parts.append(decoded)
            
            return '. '.join(translated_parts)
            
        except Exception as e:
            print(f"Translation error: {str(e)}")
            return text


def read_srt(file_path):
    segments = []
    current_segment = {'index': '', 'time': '', 'text': ''}
    current_field = 'index'
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for line in lines:
        line = line.strip()
        if not line:
            if current_segment['text']:
                segments.append(current_segment.copy())
            current_segment = {'index': '', 'time': '', 'text': ''}
            current_field = 'index'
            continue
            
        if current_field == 'index':
            current_segment['index'] = line
            current_field = 'time'
        elif current_field == 'time':
            current_segment['time'] = line
            current_field = 'text'
        else:
            current_segment['text'] = current_segment.get('text', '') + ' ' + line
            
    if current_segment['text']:
        segments.append(current_segment)
        
    return segments


def translate_segments(translator, segments, source_lang, target_lang):
    translated_segments = []
    
    with tqdm(total=len(segments), desc=f"Translating to {target_lang}", unit="segment") as pbar:
        for segment in segments:
            try:
                translated_text = translator.translate_text(
                    segment['text'],
                    source_lang,
                    target_lang
                )
                
                translated_segment = segment.copy()
                translated_segment['text'] = translated_text
                translated_segments.append(translated_segment)
                
            except Exception as e:
                print(f"Translation error for segment {segment['index']}: {str(e)}")
                translated_segments.append(segment)  # Keep original if translation fails
            
            pbar.update(1)
            
    return translated_segments


def save_srt(segments, file_path):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        for segment in segments:
            f.write(f"{segment['index']}\n")
            f.write(f"{segment['time']}\n")
            if segment.get('text'):
                f.write(f"{segment['text'].strip()}\n")
            f.write("\n")


def translate_srt(input_path, output_dir, source_lang, target_langs=['en', 'he'], output_paths=None):
    base_name = os.path.splitext(os.path.basename(input_path))[0].replace('_original', '')
    
    # Initialize translator
    translator = LocalTranslator()
    
    # Read original SRT
    print(f"\nReading original SRT file...")
    segments = read_srt(input_path)
    
    results = {}
    
    # Translate to each target language
    for target_lang in target_langs:
        try:
            if source_lang == target_lang:
                print(f"\nSkipping translation to {target_lang} (same as source language)")
                continue
            
            # Use predefined path if available, otherwise construct one
            if output_paths and target_lang in output_paths:
                output_path = output_paths[target_lang]
            else:
                output_path = os.path.join(output_dir, f'{base_name}_{target_lang}.srt')
                
            print(f"\nTranslating to {target_lang}...")
            
            translated_segments = translate_segments(
                translator,
                segments,
                source_lang,
                target_lang
            )
            
            print(f"Saving {target_lang} translation to {output_path}...")
            save_srt(translated_segments, output_path)
            
            results[target_lang] = {
                'path': output_path,
                'size': os.path.getsize(output_path),
                'segments_translated': len(translated_segments)
            }
            
        except Exception as e:
            print(f"Error translating to {target_lang}: {str(e)}")
            
    return results
