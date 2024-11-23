from google.cloud import storage
import json
import os
from datetime import datetime


class StorageManager:
    def __init__(self, bucket_name):
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)

    def list_videos(self, prefix):
        video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.webm')
        blobs = self.bucket.list_blobs(prefix=prefix)
        return [
            blob.name for blob in blobs
            if any(blob.name.lower().endswith(ext) for ext in video_extensions)
        ]

    def download_video(self, source_blob_name, destination):
        try:
            print(f"Downloading: {source_blob_name}")
            blob = self.bucket.blob(source_blob_name)
            blob.download_to_filename(destination)
            
            # Verify download
            if not os.path.exists(destination):
                raise Exception("Download failed: File not found")
            if os.path.getsize(destination) == 0:
                raise Exception("Download failed: Empty file")
                
        except Exception as e:
            raise Exception(f"Download error: {str(e)}")

    def upload_file(self, source, destination_blob_name):
        try:
            print(f"Uploading to: {destination_blob_name}")
            
            # Create directory structure if needed
            directory = os.path.dirname(destination_blob_name)
            if directory:
                placeholder = self.bucket.blob(f"{directory}/.placeholder")
                if not placeholder.exists():
                    placeholder.upload_from_string('')

            # Upload file
            blob = self.bucket.blob(destination_blob_name)
            blob.upload_from_filename(source)
            
        except Exception as e:
            raise Exception(f"Upload error: {str(e)}")

    def get_processed_files(self, metadata_path):
        try:
            blob = self.bucket.blob(metadata_path)
            if blob.exists():
                return json.loads(blob.download_as_string())
            return {}
        except Exception:
            return {}

    def save_metadata(self, metadata, path):
        try:
            # Ensure directory exists
            directory = os.path.dirname(path)
            if directory:
                placeholder = self.bucket.blob(f"{directory}/.placeholder")
                if not placeholder.exists():
                    placeholder.upload_from_string('')

            # Save metadata
            blob = self.bucket.blob(path)
            blob.upload_from_string(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                content_type='application/json'
            )
        except Exception as e:
            raise Exception(f"Metadata save error: {str(e)}")

    def update_processed_files(self, video_path, info, metadata_path):
        lock_path = f"{os.path.dirname(metadata_path)}/update.lock"
        lock_blob = self.bucket.blob(lock_path)

        try:
            # Acquire lock
            lock_blob.upload_from_string('locked', if_generation_match=0)

            # Get or create processed files list
            try:
                processed_files = self.get_processed_files(metadata_path)
            except Exception:
                processed_files = {}

            # Update with new info
            processed_files[video_path] = info

            # Save updated list
            self.save_metadata(processed_files, metadata_path)

        except Exception as e:
            raise Exception(f"Update error: {str(e)}")

        finally:
            # Release lock
            try:
                lock_blob.delete()
            except Exception:
                pass

