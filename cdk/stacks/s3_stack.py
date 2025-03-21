from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_iam as iam,
    RemovalPolicy,
    CfnOutput,
    Duration
)
from constructs import Construct

class S3Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Bucket dla danych IoT
        self.bucket = s3.Bucket(
            self, "IoTDataBucket",
            bucket_name=f"iot-data-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=Duration.days(30)  # Dane starsze niż 30 dni są usuwane
                )
            ]
        )

        # Output dla nazwy bucketa
        CfnOutput(
            self, "BucketName",
            value=self.bucket.bucket_name,
            description="Nazwa bucketa S3 dla danych IoT"
        )