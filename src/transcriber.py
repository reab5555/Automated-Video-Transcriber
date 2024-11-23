import os
import subprocess
import json
from tqdm import tqdm
import whisper
import torch
from datetime import datetime, timedelta
from src.translator import translate_srt

def format_timestamp(seconds):
    td = timedelta(seconds=seconds)
    hours = td.seconds//3600
    minutes = (td.seconds//60)%60
    seconds = td.seconds%60
    milliseconds = td.microseconds//1000
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def save_as_srt(segments, file_path):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments, 1):
            # Convert start and end times to SRT format
            start_time = format_timestamp(segment['start'])
            end_time = format_timestamp(segment['end'])
            
            # Write SRT segment
            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{segment['text'].strip()}\n\n")


class AudioProcessor:
    def __init__(self, device=None, model_name="turbo"):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.model_name = model_name
        print(f"Initializing AudioProcessor...")
        print(f"Using device: {device}")
        
        # Initialize Whisper model
        print(f"Loading whisper {model_name} model...")
        self.model = whisper.load_model(model_name).to(device)
        print("Model loaded successfully")

    def get_audio_info(self, audio_path):
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-show_entries', 'stream=sample_rate',
                '-of', 'json',
                audio_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            
            return {
                'duration': float(info['format']['duration']),
                'file_size': os.path.getsize(audio_path),
                'sample_rate': int(info['streams'][0]['sample_rate'])
            }
        except Exception as e:
            raise Exception(f"Error getting audio info: {str(e)}")

    def extract_audio(self, video_path, audio_path):
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        try:
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-vn',  # No video
                '-acodec', 'pcm_s16le',  # PCM 16-bit
                '-ar', '16000',  # 16kHz sample rate
                '-ac', '1',  # Mono
                '-y',  # Overwrite output
                audio_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                raise Exception("Audio extraction failed")
                
        except subprocess.CalledProcessError as e:
            raise Exception(f"FFmpeg error: {e.stderr}")
        except Exception as e:
            raise Exception(f"Audio extraction error: {str(e)}")

    def transcribe_audio(self, audio_path, output_path, callback=None):
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        try:
            info = self.get_audio_info(audio_path)
            print("\nAudio information:")
            print(f"Duration: {info['duration']:.2f} seconds")
            
            # Load audio file
            audio = whisper.load_audio(audio_path)
            
            # Calculate chunks - 1 minute each
            CHUNK_LENGTH_SECONDS = 60
            chunk_length = CHUNK_LENGTH_SECONDS * 16000
            chunks = [audio[i:i + chunk_length] for i in range(0, len(audio), chunk_length)]
            total_chunks = len(chunks)
            print(f"\nProcessing {total_chunks} chunks of {CHUNK_LENGTH_SECONDS} seconds each...")

            # First chunk for language detection
            print("\nDetecting language...")
            initial_result = self.model.transcribe(
                chunks[0],
                language=None,
                task="transcribe",
                fp16=torch.cuda.is_available()
            )
            detected_language = initial_result["language"]
            print(f"Detected language: {detected_language}")

            # Process transcription
            print("\nTranscribing in original language...")
            all_segments = []
            current_time = 0
            
            with tqdm(total=total_chunks, desc="Transcription Processing", unit="chunk") as pbar:
                for i, chunk in enumerate(chunks):
                    result = self.model.transcribe(
                        chunk,
                        language=detected_language,
                        task="transcribe",
                        fp16=torch.cuda.is_available(),
                        verbose=False
                    )

                    # Process segments
                    for segment in result["segments"]:
                        segment['start'] += current_time
                        segment['end'] += current_time
                    
                    all_segments.extend(result["segments"])
                    current_time += len(chunk) / 16000
                    
                    pbar.update(1)
                    if callback:
                        progress = (i + 1) / len(chunks) * 100
                        callback(progress)

            # Filter out empty segments
            all_segments = [seg for seg in all_segments if seg['text'].strip()]
            
            # Save transcription
            print(f"\nSaving transcription...")
            save_as_srt(all_segments, output_path)

            results = {
                'input_size': info['file_size'],
                'output_size': os.path.getsize(output_path),
                'duration': info['duration'],
                'detected_language': detected_language,
                'chunks_processed': total_chunks,
                'chunk_size_seconds': CHUNK_LENGTH_SECONDS
            }

            print("\nTranscription results:")
            print(f"Detected language: {detected_language}")
            print(f"Total chunks processed: {total_chunks}")
            print(f"Chunk size: {CHUNK_LENGTH_SECONDS} seconds")
            print(f"Input file size: {results['input_size']/1024/1024:.2f}MB")
            print(f"Output SRT size: {results['output_size']/1024:.2f}KB")

            return results, detected_language

        except Exception as e:
            raise Exception(f"Transcription error: {str(e)}")

    def process_video(self, input_path, output_dir, callback=None):
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Create output paths
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        os.makedirs(output_dir, exist_ok=True)

        # Create all output paths in the same directory
        output_paths = {
            'original': os.path.join(output_dir, f'{base_name}_original.srt'),
            'en': os.path.join(output_dir, f'{base_name}_english.srt'),
            'he': os.path.join(output_dir, f'{base_name}_hebrew.srt')
        }

        # Create temporary audio file
        temp_audio = os.path.join(output_dir, 'temp_audio.wav')

        try:
            # Extract audio
            print("\nExtracting audio from video...")
            self.extract_audio(input_path, temp_audio)

            # Transcribe
            print("\nStarting transcription...")
            results, detected_language = self.transcribe_audio(
                temp_audio,
                output_paths['original'],
                callback
            )

            # Now translate using the local translator
            print("\nTranslating transcriptions...")
            translate_srt(
                input_path=output_paths['original'],    # Original SRT
                output_dir=output_dir,                  # Same output directory
                source_lang=detected_language,          # Source language from Whisper
                target_langs=['en', 'he'],             # Target languages
                output_paths=output_paths              # Pass the pre-defined paths
            )

            return results, detected_language
            
        finally:
            # Cleanup temporary audio file
            if os.path.exists(temp_audio):
                os.remove(temp_audio)