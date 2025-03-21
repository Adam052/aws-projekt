from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3_assets as assets,
    CfnOutput,
    Tags,
)
from constructs import Construct
import os
import shutil
import tempfile

class EC2Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, vpc: ec2.Vpc, msk_stack, s3_stack, bedrock_stack=None, iot_stack=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Utwórz tymczasowy katalog z potrzebnymi plikami
        tmp_dir = tempfile.mkdtemp()
        try:
            # Kopiuj tylko potrzebne pliki
            shutil.copytree(
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "iot"),
                os.path.join(tmp_dir, "iot"),
                dirs_exist_ok=True
            )
            shutil.copy2(
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "pyproject.toml"),
                os.path.join(tmp_dir, "pyproject.toml")
            )
            shutil.copy2(
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "poetry.lock"),
                os.path.join(tmp_dir, "poetry.lock")
            )

            # Utwórz asset z tymczasowego katalogu
            app_asset = assets.Asset(
                self, "AppCode",
                path=tmp_dir
            )
        except Exception as e:
            # W przypadku błędu wyczyść katalog tymczasowy
            shutil.rmtree(tmp_dir)
            raise e
        finally:
            # Wyczyść tymczasowy katalog
            shutil.rmtree(tmp_dir)

        # Role dla EC2 - połącz wszystkie potrzebne uprawnienia
        subscriber_role = iam.Role(
            self, "EC2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com")
        )

        # Dodanie wszystkich potrzebnych polityk
        subscriber_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AWSIoTFullAccess")
        )
        subscriber_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonMSKFullAccess")
        )
        subscriber_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        )
        subscriber_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("EC2InstanceConnect")
        )

        # Dodaj politykę S3 przed tworzeniem instancji
        subscriber_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess")
        )

        # Dodaj uprawnienia dla assetu
        app_asset.grant_read(subscriber_role)

        # Dodaj politykę Bedrock
        subscriber_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess")
        )

        # Dodaj politykę dla dostępu do S3 i MSK
        subscriber_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "kafka:ListClusters",
                "kafka:GetBootstrapBrokers",
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            resources=[
                f"arn:aws:kafka:{self.region}:{self.account}:cluster/*",
                f"arn:aws:s3:::{s3_stack.bucket.bucket_name}",
                f"arn:aws:s3:::{s3_stack.bucket.bucket_name}/*"
            ]
        ))

        # Security Group dla EC2
        security_group = ec2.SecurityGroup(
            self, "SecurityGroup",
            vpc=vpc,
            allow_all_outbound=True,
            description="Security group for EC2 instances"
        )

        # Dodaj regułę dla SSH
        security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(22),
            description="Allow SSH access from anywhere"
        )

        # Dodaj reguły dla MSK
        security_group.add_egress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9092),  # Port dla plaintext
            description="Allow outbound to MSK plaintext"
        )
        security_group.add_egress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9094),  # Port dla TLS
            description="Allow outbound to MSK TLS"
        )
        security_group.add_egress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9096),  # Port dla SASL
            description="Allow outbound to MSK SASL"
        )

        # Dodaj regułę dla MSK
        security_group.add_egress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9094),
            description="Allow outbound to MSK TLS"
        )

        # Dodaj regułę dla MSK Security Group
        security_group.connections.allow_to(
            msk_stack.security_group,
            ec2.Port.tcp(9094),
            "Allow outbound to MSK TLS"
        )

        # Dodaj tag do security group
        Tags.of(security_group).add(
            "Name", "EC2-SecurityGroup"
        )

        # User data dla Publisher EC2
        publisher_user_data = ec2.UserData.for_linux()
        publisher_user_data.add_commands(
            "set -ex",  # Pokaż wykonywane komendy i zakończ przy błędzie

            # Logowanie do wielu miejsc
            "exec > >(tee -a /var/log/user-data.log /var/log/cloud-init-output.log) 2>&1",
            "echo 'Starting user-data script...'",

            # Funkcja do logowania i przerywania w przypadku błędu
            "function error_exit() {",
            "  echo \"ERROR: $1\" | tee -a /var/log/user-data.log /var/log/cloud-init-output.log",
            "  echo \"Deployment failed\" | tee -a /var/log/user-data.log /var/log/cloud-init-output.log",
            "  sync",  # Wymusza zapis logów na dysk
            "  exit 1",
            "}",

            # Funkcja do logowania
            "function log() {",
            "  echo \"$(date '+%Y-%m-%d %H:%M:%S'): $1\" | tee -a /var/log/user-data.log /var/log/cloud-init-output.log",
            "  sync",
            "}",

            # Aktualizacja systemu i instalacja pakietów
            "log 'Installing required packages...'",
            "yum install -y python3-pip git unzip java-11-amazon-corretto || error_exit 'Failed to install required packages'",

            # Instalacja narzędzi Kafka
            "log 'Installing Kafka tools...'",
            "KAFKA_VERSION=2.8.1",
            "curl -O https://archive.apache.org/dist/kafka/${KAFKA_VERSION}/kafka_2.13-${KAFKA_VERSION}.tgz || error_exit 'Failed to download Kafka'",
            "tar -xzf kafka_2.13-${KAFKA_VERSION}.tgz || error_exit 'Failed to extract Kafka'",
            "mv kafka_2.13-${KAFKA_VERSION} /opt/kafka || error_exit 'Failed to move Kafka'",
            "rm kafka_2.13-${KAFKA_VERSION}.tgz || error_exit 'Failed to cleanup Kafka archive'",
            "echo 'export PATH=$PATH:/opt/kafka/bin' >> /etc/profile.d/kafka.sh || error_exit 'Failed to set Kafka PATH'",
            "source /etc/profile.d/kafka.sh || error_exit 'Failed to reload PATH'",

            # Instalacja Poetry przez pip
            "log 'Installing Poetry...'",
            "python3 -m pip install --user poetry || error_exit 'Failed to install poetry'",

            # Przygotowanie aplikacji
            "log 'Creating app directory...'",
            f"mkdir -p /opt/iot-app || error_exit 'Failed to create app directory'",
            f"cd /opt/iot-app || error_exit 'Failed to change directory'",

            "log 'Downloading app code...'",
            f"aws s3 cp s3://{app_asset.s3_bucket_name}/{app_asset.s3_object_key} app.zip || error_exit 'Failed to download app code'",
            f"unzip -o app.zip || error_exit 'Failed to unzip app code'",

            # Instalacja zależności
            "log 'Installing dependencies...'",
            "cd /opt/iot-app || error_exit 'Failed to change directory'",
            "/root/.local/bin/poetry env use python3 || error_exit 'Failed to set Python version'",
            "/root/.local/bin/poetry install --no-interaction || error_exit 'Failed to install dependencies'",

            # Dodaj log aby zobaczyć wartość
            f"echo 'MSK brokers: {msk_stack.cluster.bootstrap_brokers_tls}' >> /var/log/user-data.log",

            # Utwórz plik logów
            "log 'Creating log file...'",
            "touch /var/log/iot-publisher.log || error_exit 'Failed to create log file'",
            "chown root:root /var/log/iot-publisher.log || error_exit 'Failed to set log file permissions'",
            "chmod 644 /var/log/iot-publisher.log || error_exit 'Failed to set log file permissions'",

            # Konfiguracja serwisu
            f"cat > /etc/systemd/system/iot-publisher.service << EOF || error_exit 'Failed to create service file'\n"
            "[Unit]\n"
            "Description=IoT Publisher Service\n"
            "After=network.target\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            "WorkingDirectory=/opt/iot-app\n"
            f"Environment=\"AWS_REGION={self.region}\"\n"
            f"Environment=\"MSK_CLUSTER_ARN={msk_stack.cluster.cluster_arn}\"\n"
            f"Environment=\"MSK_BOOTSTRAP_BROKERS={msk_stack.bootstrap_brokers_tls}\"\n"
            "StandardOutput=journal+append:/var/log/iot-publisher.log\n"
            "StandardError=journal+append:/var/log/iot-publisher.log\n"
            "Environment=\"PATH=/root/.local/bin:$PATH\"\n"
            "ExecStart=/root/.local/bin/poetry run python iot/publisher/main.py\n"
            "Restart=always\n"
            "User=root\n"
            "\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
            "EOF",

            # Sprawdź zawartość pliku serwisu
            "echo 'Service file contents:' >> /var/log/user-data.log",
            "cat /etc/systemd/system/iot-publisher.service >> /var/log/user-data.log",

            # Ustawienie uprawnień
            "log 'Setting permissions...'",
            "chown -R root:root /opt/iot-app || error_exit 'Failed to set permissions'",

            # Uruchomienie serwisu
            "log 'Starting service...'",
            "systemctl daemon-reload || error_exit 'Failed to reload systemd'",
            "systemctl enable iot-publisher || error_exit 'Failed to enable service'",
            "systemctl start iot-publisher || error_exit 'Failed to start service'",

            # Weryfikacja statusu
            "log 'Verifying service status...'",
            "systemctl is-active iot-publisher || error_exit 'Service not running'",

            "log 'User-data script completed successfully'"
        )

        # Instancje EC2
        self.publisher_instance = ec2.Instance(
            self, "PublisherInstance",
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
            machine_image=ec2.AmazonLinuxImage(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2023
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=security_group,
            role=subscriber_role,
            user_data=publisher_user_data,
            associate_public_ip_address=True
        )

        # Po utworzeniu publisher_instance, dodaj subscriber:
        subscriber_user_data = ec2.UserData.for_linux()
        subscriber_user_data.add_commands(
            "#!/bin/bash",
            "set -ex",
            "exec > >(tee -a /var/log/user-data.log /var/log/cloud-init-output.log) 2>&1",
            "echo 'Starting user-data script...'",
            "function error_exit() {",
            "  echo \"ERROR: $1\" | tee -a /var/log/user-data.log /var/log/cloud-init-output.log",
            "  echo \"Deployment failed\" | tee -a /var/log/user-data.log /var/log/cloud-init-output.log",
            "  sync",
            "  exit 1",
            "}",
            "function log() {",
            "  echo \"$(date '+%Y-%m-%d %H:%M:%S'): $1\" | tee -a /var/log/user-data.log /var/log/cloud-init-output.log",
            "  sync",
            "}",
            "log 'Installing required packages...'",
            "yum install -y python3-pip git unzip java-11-amazon-corretto || error_exit 'Failed to install required packages'",
            "log 'Installing Kafka tools...'",
            "KAFKA_VERSION=2.8.1",
            "curl -O https://archive.apache.org/dist/kafka/${KAFKA_VERSION}/kafka_2.13-${KAFKA_VERSION}.tgz || error_exit 'Failed to download Kafka'",
            "tar -xzf kafka_2.13-${KAFKA_VERSION}.tgz || error_exit 'Failed to extract Kafka'",
            "mv kafka_2.13-${KAFKA_VERSION} /opt/kafka || error_exit 'Failed to move Kafka'",
            "rm kafka_2.13-${KAFKA_VERSION}.tgz || error_exit 'Failed to cleanup Kafka archive'",
            "echo 'export PATH=$PATH:/opt/kafka/bin' >> /etc/profile.d/kafka.sh || error_exit 'Failed to set Kafka PATH'",
            "source /etc/profile.d/kafka.sh || error_exit 'Failed to reload PATH'",
            "log 'Installing Poetry...'",
            "python3 -m pip install --user poetry || error_exit 'Failed to install poetry'",
            "log 'Creating app directory...'",
            "mkdir -p /opt/iot-app || error_exit 'Failed to create app directory'",
            "cd /opt/iot-app || error_exit 'Failed to change directory'",
            "log 'Downloading app code...'",
            f"aws s3 cp s3://{app_asset.s3_bucket_name}/{app_asset.s3_object_key} app.zip || error_exit 'Failed to download app code'",
            "unzip -o app.zip || error_exit 'Failed to unzip app code'",
            "log 'Installing dependencies...'",
            "cd /opt/iot-app || error_exit 'Failed to change directory'",
            "/root/.local/bin/poetry env use python3 || error_exit 'Failed to set Python version'",
            "/root/.local/bin/poetry install --no-interaction || error_exit 'Failed to install dependencies'",
            "log 'Creating log files...'",
            "touch /var/log/iot-subscriber.log || error_exit 'Failed to create log file'",
            "chown root:root /var/log/iot-subscriber.log || error_exit 'Failed to set log file permissions'",
            "chmod 644 /var/log/iot-subscriber.log || error_exit 'Failed to set log file permissions'",
            "cat > /etc/systemd/system/iot-subscriber.service << EOF || error_exit 'Failed to create service file'",
            "[Unit]",
            "Description=IoT Subscriber Service",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            "WorkingDirectory=/opt/iot-app",
            f"Environment=\"AWS_REGION={self.region}\"",
            f"Environment=\"MSK_CLUSTER_ARN={msk_stack.cluster.cluster_arn}\"",
            f"Environment=\"S3_BUCKET_NAME={s3_stack.bucket.bucket_name}\"",
            f"Environment=\"MSK_BOOTSTRAP_BROKERS={msk_stack.bootstrap_brokers_tls}\"",
            "StandardOutput=append:/var/log/iot-subscriber.log",
            "StandardError=append:/var/log/iot-subscriber.log",
            "Environment=\"PATH=/root/.local/bin:$PATH\"",
            "ExecStart=/root/.local/bin/poetry run python iot/subscriber/main.py",
            "Restart=always",
            "RestartSec=10",
            "StartLimitInterval=0",
            "User=root",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "EOF",
            "log 'Setting permissions...'",
            "chown -R root:root /opt/iot-app || error_exit 'Failed to set permissions'",
            "log 'Starting service...'",
            "systemctl daemon-reload || error_exit 'Failed to reload systemd'",
            "systemctl enable iot-subscriber || error_exit 'Failed to enable service'",
            "systemctl start iot-subscriber || error_exit 'Failed to start service'",
            "log 'Verifying service status...'",
            "systemctl is-active iot-subscriber || error_exit 'Service not running'",
            "log 'User-data script completed successfully'"
        )

        self.subscriber_instance = ec2.Instance(
            self, "SubscriberInstance",
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
            machine_image=ec2.AmazonLinuxImage(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2023
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=security_group,
            role=subscriber_role,
            user_data=subscriber_user_data,
            associate_public_ip_address=True
        )

        # Dodaj outputy dla EC2
        CfnOutput(self, "PublisherInstanceId",
            value=self.publisher_instance.instance_id,
            description="ID instancji EC2 publishera"
        )

        CfnOutput(self, "PublisherPublicIP",
            value=self.publisher_instance.instance_public_dns_name,
            description="Publiczne DNS publishera"
        )

        CfnOutput(self, "PublisherPrivateIP",
            value=self.publisher_instance.instance_private_dns_name,
            description="Prywatne DNS publishera"
        )

        # Dodaj output dla Subscriber EC2
        CfnOutput(self, "SubscriberInstanceId",
            value=self.subscriber_instance.instance_id,
            description="ID instancji EC2 subscribera"
        )

        CfnOutput(self, "SubscriberPublicIP",
            value=self.subscriber_instance.instance_public_dns_name,
            description="Publiczne DNS subscribera"
        )

        # Dodaj output dla Session Manager
        CfnOutput(
            self, "ConnectPublisherCommand",
            value=f"aws ssm start-session --target {self.publisher_instance.instance_id}",
            description="Komenda do połączenia z Publisher EC2 przez Session Manager"
        )

        CfnOutput(
            self, "ConnectSubscriberCommand",
            value=f"aws ssm start-session --target {self.subscriber_instance.instance_id}",
            description="Komenda do połączenia z Subscriber EC2 przez Session Manager"
        )
