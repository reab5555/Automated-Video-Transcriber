import os
import uuid
import shutil
from datetime import datetime
from tqdm import tqdm
from src.transcriber import AudioProcessor
from src.storage_manager import StorageManager
from src.logger import ProcessingLogger

# Create a temporary directory for processing files
def setup_temp_dir():
    temp_dir = f'/tmp/transcription_{uuid.uuid4().hex[:8]}'
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

# Get the next unprocessed video file from storage
def get_next_file_to_process(storage, input_prefix, metadata_prefix):
    all_videos = storage.list_videos(input_prefix)
    processed_files = storage.get_processed_files(metadata_prefix)

    for video in all_videos:
        if video not in processed_files:
            try:
                # Mark file as being processed
                storage.update_processed_files(video, {"status": "processing"}, metadata_prefix)
                return video
            except Exception as e:
                print(f"Failed to lock file {video}: {e}")
                continue
    return None


def process_video(video_path, storage, processor, logger, input_prefix, output_prefix, metadata_prefix):
    temp_dir = setup_temp_dir()
    
    # Use the original filename
    original_filename = os.path.basename(video_path)
    base_name = os.path.splitext(original_filename)[0]
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    input_path = os.path.join(temp_dir, original_filename)

    start_time = datetime.now()
    try:
        # Download video
        print(f"\nDownloading: {video_path}")
        storage.download_video(video_path, input_path)

        # Process video - creates all three SRT files
        print("\nStarting transcription...")
        results, detected_language = processor.process_video(input_path, temp_dir)

        # Prepare GCS paths
        video_gcs_dir = f"{output_prefix}{current_date}/{base_name}/"
        
        # Upload all three SRT files
        outputs = {}
        for lang_type in ['original', 'english', 'hebrew']:
            source_file = os.path.join(temp_dir, f"{base_name}_{lang_type}.srt")
            
            # Verify file exists before uploading
            if not os.path.exists(source_file):
                print(f"Warning: {lang_type} SRT file not found at {source_file}")
                continue
                
            dest_path = f"{video_gcs_dir}{base_name}_{lang_type}.srt"
            print(f"Uploading to: {dest_path}")
            storage.upload_file(source_file, dest_path)
            outputs[lang_type] = dest_path

        # Update metadata
        metadata = {
            'processed_date': current_date,
            'output_paths': outputs,
            'success': True,
            'processing_results': results,
            'detected_language': detected_language
        }
        storage.update_processed_files(video_path, metadata, metadata_prefix)

        # Log success
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.log_transcription(video_path, True, processing_time, results)
        print(f"✓ Success: {video_path}")
        return True

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.log_transcription(video_path, False, processing_time, error=str(e))
        print(f"Error processing {video_path}: {e}")
        return False

    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    # Configuration
    bucket_name = os.getenv('BUCKET_NAME', 'main_il')
    input_prefix = os.getenv('INPUT_PREFIX', 'transcription_workplace/input_directory/')
    output_prefix = os.getenv('OUTPUT_PREFIX', 'transcription_workplace/output_directory/')
    metadata_prefix = os.getenv('METADATA_PREFIX', 'transcription_workplace/metadata_directory/')

    print("\nVideo Transcription System Starting...")
    print(f"Bucket: {bucket_name}")
    print(f"Input prefix: {input_prefix}")
    print(f"Output prefix: {output_prefix}")

    # Initialize components
    storage = StorageManager(bucket_name)
    processor = AudioProcessor()
    logger = ProcessingLogger(storage, metadata_prefix)

    # Get list of videos to process
    all_videos = storage.list_videos(input_prefix)
    total_videos = len(all_videos)
    processed_videos = 0

    print(f"\nFound {total_videos} videos to process")

    # Process videos with progress bar
    with tqdm(total=total_videos, desc="Processing Files", unit="file") as pbar:
        while True:
            video_path = get_next_file_to_process(storage, input_prefix, metadata_prefix)
            
            if not video_path:
                print("\nNo more videos to process. Exiting...")
                break

            print(f"\nProcessing video: {video_path}")
            if process_video(
                video_path, storage, processor, logger,
                input_prefix, output_prefix, metadata_prefix
            ):
                processed_videos += 1
                pbar.update(1)

    # Save final logs
    logger.save_logs()
    print(f"\nProcessed {processed_videos}/{total_videos} videos")


if __name__ == "__main__":
    start_time = datetime.now()
    try:
        main()
    finally:
        duration = datetime.now() - start_time
        print(f"\nTotal runtime: {duration}")