from datetime import datetime
import json
import platform
import torch


class ProcessingLogger:
    def __init__(self, storage_manager, metadata_prefix):
        """Initialize the logger with storage manager and metadata prefix"""
        self.storage = storage_manager
        self.metadata_prefix = metadata_prefix
        self.current_date = datetime.now().strftime('%Y-%m-%d')
        
        # Initialize log structure
        self.logs = {
            "date": self.current_date,
            "system_info": {
                "platform": platform.system(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "cuda_available": torch.cuda.is_available(),
                "cuda_version": torch.version.cuda if torch.cuda.is_available() else None,
                "gpu_devices": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if torch.cuda.is_available() else []
            },
            "model_info": {
                "name": "whisper-large-v3-turbo",
                "provider": "OpenAI/Transformers"
            },
            "files_processed": 0,
            "successful": 0,
            "failed": 0,
            "total_duration_processed": 0,
            "total_processing_time": 0,
            "processing_details": []
        }

    def log_transcription(self, video_path, success, processing_time, details=None, error=None):
        """Log a transcription attempt"""
        log_entry = {
            "file": video_path,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "success": success,
            "processing_time_seconds": processing_time
        }

        if success and details:
            # Add successful transcription details
            log_entry.update({
                "input_size_bytes": details['input_size'],
                "output_size_bytes": details['output_size'],
                "duration_seconds": details['duration'],
                "chunks_processed": details['chunks_processed'],
                "processing_speed": details['duration'] / processing_time if processing_time > 0 else 0
            })
            self.logs["successful"] += 1
            self.logs["total_duration_processed"] += details['duration']
        else:
            # Add error information
            log_entry["error"] = str(error)
            self.logs["failed"] += 1

        self.logs["files_processed"] += 1
        self.logs["total_processing_time"] += processing_time
        self.logs["processing_details"].append(log_entry)

    def save_logs(self):
        """Save logs to storage and update cumulative statistics"""
        # Calculate additional statistics
        if self.logs["files_processed"] > 0:
            self.logs["statistics"] = {
                "success_rate": (self.logs["successful"] / self.logs["files_processed"]) * 100,
                "average_processing_time": self.logs["total_processing_time"] / self.logs["files_processed"],
                "total_hours_processed": self.logs["total_duration_processed"] / 3600
            }

        # Save daily log
        daily_log_path = f"{self.metadata_prefix}logs/{self.current_date}_processing_log.json"
        self.storage.save_metadata(self.logs, daily_log_path)

        try:
            # Update cumulative statistics
            stats_path = f"{self.metadata_prefix}stats.json"
            try:
                stats = self.storage.get_processed_files(stats_path)
            except Exception:
                stats = {"created_date": self.current_date}

            # Update cumulative stats
            stats.update({
                "total_processed": stats.get("total_processed", 0) + self.logs["files_processed"],
                "total_successful": stats.get("total_successful", 0) + self.logs["successful"],
                "total_failed": stats.get("total_failed", 0) + self.logs["failed"],
                "total_duration_processed": stats.get("total_duration_processed", 0) + self.logs["total_duration_processed"],
                "total_processing_time": stats.get("total_processing_time", 0) + self.logs["total_processing_time"],
                "last_update": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

            # Calculate cumulative statistics
            if stats["total_processed"] > 0:
                stats["cumulative_statistics"] = {
                    "overall_success_rate": (stats["total_successful"] / stats["total_processed"]) * 100,
                    "average_processing_time": stats["total_processing_time"] / stats["total_processed"],
                    "total_hours_processed": stats["total_duration_processed"] / 3600
                }

            self.storage.save_metadata(stats, stats_path)
            
        except Exception as e:
            print(f"Error updating cumulative stats: {e}")
