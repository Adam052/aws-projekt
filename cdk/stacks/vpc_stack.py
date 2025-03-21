from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput,
    RemovalPolicy,
)
from constructs import Construct

class VPCStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Tworzenie VPC
        self.vpc = ec2.Vpc(
            self, "IoTVPC",
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                )
            ]
        )

        # Dodaj politykę usuwania dla VPC i jego komponentów
        self.vpc.apply_removal_policy(RemovalPolicy.DESTROY)

        # Dodaj politykę usuwania dla wszystkich subnetów
        for subnet in self.vpc.private_subnets + self.vpc.public_subnets:
            subnet.apply_removal_policy(RemovalPolicy.DESTROY)

        # Outputy
        CfnOutput(self, "VPCId",
            value=self.vpc.vpc_id,
            export_name=f"{construct_id}:VPCId"
        )

        CfnOutput(self, "PrivateSubnet1Id",
            value=self.vpc.private_subnets[0].subnet_id,
            export_name=f"{construct_id}:PrivateSubnet1Id"
        )

        CfnOutput(self, "PrivateSubnet2Id",
            value=self.vpc.private_subnets[1].subnet_id,
            export_name=f"{construct_id}:PrivateSubnet2Id"
        )