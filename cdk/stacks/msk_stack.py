from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput,
    RemovalPolicy,
    Tags,
)
import aws_cdk.aws_msk_alpha as msk
from constructs import Construct

class MSKStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, vpc=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Najpierw utwórz Security Group
        self.security_group = ec2.SecurityGroup(
            self, "MSKSecurityGroup",
            vpc=vpc,
            description="Security group for MSK cluster",
            allow_all_outbound=True
        )
        # Dodaj politykę usuwania po utworzeniu
        self.security_group.apply_removal_policy(RemovalPolicy.DESTROY)

        # Dodaj regułę dla EC2
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9092),
            description="Allow inbound from EC2 plaintext"
        )
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9094),
            description="Allow inbound from EC2 TLS"
        )
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9096),
            description="Allow inbound from EC2 SASL"
        )

        # Dodaj tag do security group
        Tags.of(self.security_group).add(
            "Name", "MSK-SecurityGroup"
        )

        # Konfiguracja klastra MSK
        self.cluster = msk.Cluster(
            self, "MSKCluster",
            cluster_name=f"msk-{construct_id.lower()}",
            kafka_version=msk.KafkaVersion.V2_8_1,
            vpc=vpc,
            encryption_in_transit=msk.EncryptionInTransitConfig(
                client_broker=msk.ClientBrokerEncryption.TLS
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.SMALL
            ),
            number_of_broker_nodes=2,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[self.security_group],
            removal_policy=RemovalPolicy.DESTROY
        )

        self.bootstrap_brokers_tls = self.cluster.bootstrap_brokers_tls

        # Debug output
        print(f"DEBUG: Bootstrap brokers TLS: {self.cluster.bootstrap_brokers_tls}")

        # Outputy
        CfnOutput(self, "MSKClusterArn",
            value=self.cluster.cluster_arn,
            description="ARN klastra MSK"
        )

        CfnOutput(self, "MSKBootstrapBrokers",
            value=self.cluster.bootstrap_brokers_tls,
            description="Bootstrap brokers MSK (TLS)"
        )

        CfnOutput(self, "BootstrapBrokersTls",
            value=self.cluster.bootstrap_brokers_tls,
            description="MSK Bootstrap Brokers TLS"
        )

        # Zapisz VPC jako atrybut klasy
        self.vpc = vpc