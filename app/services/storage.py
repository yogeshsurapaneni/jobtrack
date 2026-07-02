from minio import Minio
from minio.error import S3Error
import io

class StorageService:
    def __init__(self, app=None):
        self.client = None
        self.bucket = None
        if app:
            self.init_app(app)

    def init_app(self, app):
        endpoint = app.config['MINIO_ENDPOINT']
        access_key = app.config['MINIO_ACCESS_KEY']
        secret_key = app.config['MINIO_SECRET_KEY']
        secure = app.config['MINIO_SECURE']
        self.bucket = app.config['MINIO_BUCKET']

        # The MinIO SDK only accepts "host:port" — strip any scheme (http:// / https://)
        # and trailing slashes that would cause "path in endpoint is not allowed".
        if endpoint.startswith('https://'):
            secure = True
            endpoint = endpoint[len('https://'):]
        elif endpoint.startswith('http://'):
            secure = False
            endpoint = endpoint[len('http://'):]
        endpoint = endpoint.rstrip('/')

        try:
            # Initialize client
            self.client = Minio(
                endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure
            )
            # Create bucket if it does not exist
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                print(f"[*] MinIO Bucket '{self.bucket}' created.")
            else:
                print(f"[*] MinIO Bucket '{self.bucket}' already exists.")
        except Exception as e:
            print(f"[!] Error initializing MinIO client: {e}")

    def upload_file(self, object_name, data_bytes, content_type='application/octet-stream'):
        """
        Uploads file bytes to MinIO
        """
        if not self.client:
            raise Exception("Storage client is not initialized")
        
        data_stream = io.BytesIO(data_bytes)
        length = len(data_bytes)
        
        try:
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=data_stream,
                length=length,
                content_type=content_type
            )
            return f"{self.bucket}/{object_name}"
        except S3Error as err:
            print(f"[!] MinIO S3Error during upload: {err}")
            raise err

    def download_file(self, object_name):
        """
        Downloads file from MinIO and returns bytes
        """
        if not self.client:
            raise Exception("Storage client is not initialized")
        
        response = None
        try:
            response = self.client.get_object(self.bucket, object_name)
            return response.read()
        except S3Error as err:
            print(f"[!] MinIO S3Error during download: {err}")
            raise err
        finally:
            if response:
                response.close()
                response.release_conn()

# Singleton instance to be imported and initialized in app/__init__.py
storage_service = StorageService()
