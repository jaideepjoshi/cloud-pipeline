# "pipe" CLI implementation

This approach does not use the `HTTP/REST API` directly. Instead, a command-line wrapper is used.

`pipe` CLI is a command line utility, distributed together with the Cloud Pipeline. It offers a variety of the commands for an easy automation of the common tasks. More details on the `pipe` command line interface are available in the [corresponding docs section](../../manual/14_CLI/14._Command-line_interface.md)

This utility can be used for any backend Cloud Provider, which is enabled for the CLoud Pipeline deployment (e.g. the command are all the same if using AWS/GCP/Azure).

The listed below [cellranger_pipe.sh](attachments/pipe_example/cellranger_pipe.sh) script, implements the "Usage scenario" using the only "pipe" command to communicate with the cloud platform.

```bash
#!/bin/bash
 
#############################################################
# Example dataset:
#   https://cloud-pipeline-oss-builds.s3.amazonaws.com/tools/cellranger/data/tiny-fastq/tiny-fastq.tgz
# Example run command:
#   cellranger.sh --fastqs ~/tiny-fastq \
#                 --transcriptome tiny \
#                 --workdir s3://my_bucket/tiny-example \
#                 --copy-back
#############################################################
 
#############################################################
# Parse options
#############################################################
POSITIONAL=()
while [[ $# -gt 0 ]]; do
key="$1"
    case $key in
        -f|--fastqs)
        FASTQS="$2"
        shift
        shift
        ;;
        -t|--transcriptome)
        TRANSCRIPTOME="$2"
        shift
        shift
        ;;
        -w|--workdir)
        WORKDIR="$2"
        shift
        shift
        ;;
        -i|--instance)
        INSTANCE_TYPE="$2"
        shift
        shift
        ;;
        -d|--disk)
        INSTANCE_DISK="$2"
        shift
        shift
        ;;
        -c|--copy-back)
        COPY_BACK=1
        shift
    esac
done
 
#############################################################
# Check prerequisites
#############################################################
if ! command -v pipe > /dev/null 2>&1; then
    cat << EOF
[ERROR] `pipe` Command Line Interface is not available.
Please follow the installation and configuration instructions, available in the Cloud Pipeline GUI:
* Login to the GUI
* Open "Settings" (from the left panel)
* Click "Get access key"
* Follow the installation instructions
EOF
    exit 1
fi
 
#############################################################
# Validate options
#############################################################
 
if [ -z "$FASTQS" ] || [ ! -d "$FASTQS" ]; then
    echo "[ERROR] Path to the fastq files is not set or is not a directory"
    exit 1
fi
 
if [ "$TRANSCRIPTOME" ]; then
    case $TRANSCRIPTOME in
        human)
        TRANSCRIPTOME_S3="s3://genome-bucket/human/transcriptome"
        ;;
        mouse)
        TRANSCRIPTOME_S3="s3://genome-bucket/mouse/transcriptome"
        ;;
        human-mouse)
        TRANSCRIPTOME_S3="s3://genome-bucket/human-mouse/transcriptome"
        ;;
        tiny)
        TRANSCRIPTOME_S3="s3://genome-bucket/tiny/transcriptome"
        ;;
        *)
        echo "[ERROR] Transcriptome name does not match the supported types: human, mouse, human-mouse, tiny"
        exit 1
        ;;
    esac
else
    echo "[ERROR] Transcriptome name is not set"
    exit 1
fi
 
if [ -z "$WORKDIR" ] || [[ "$WORKDIR" != "s3://"* ]]; then
    echo "[ERROR] S3 working directory is not set or uses an unexpected schema (s3:// shall be used)"
    exit 1
else
    WORKDIR_EXISTS=$(pipe storage ls $WORKDIR)
    if [ "$WORKDIR_EXISTS" ]; then
        echo "[ERROR] S3 working directory ($WORKDIR) already exists, please specify a new location"
        exit 1
    fi
fi
 
EXTRA_OPTIONS=()
if [ "$INSTANCE_TYPE" ]; then
    EXTRA_OPTIONS+=("--instance-type $INSTANCE_TYPE")
fi
if [ "$INSTANCE_TYPE" ]; then
    EXTRA_OPTIONS+=("--instance-disk $INSTANCE_DISK")
fi
 
#############################################################
# Transfer the local fastq files to the S3 working directory
#############################################################
FASTQS_S3="$WORKDIR/fastq/$(basename $FASTQS)"
echo "Transferring fastqs to the S3 working directory: $FASTQS -> $FASTQS_S3/"
pipe storage cp "$FASTQS" "$FASTQS_S3/" --recursive
if [ $? -ne 0 ]; then
    echo "[ERROR] Cannot upload $FASTQS to $WORKDIR"
    exit 1
fi
 
#############################################################
# Setup the paths and run options
#############################################################
RESULTS_S3="$WORKDIR/results"
DOCKER_IMAGE="ngs/cellranger:latest"
 
#############################################################
# Launch data processing
#############################################################
echo "Launch job with parameters:"
echo "fastqs:        $FASTQS_S3"
echo "transcriptome: $TRANSCRIPTOME_S3"
echo "results:       $RESULTS_S3"
 
pipe run --docker-image "$DOCKER_IMAGE" \
            --fastqs "input?$FASTQS_S3" \
            --transcriptome "input?$TRANSCRIPTOME_S3" \
            --results "output?$RESULTS_S3" \
            --cmd-template 'cellranger count --id cloud-cellranger --fastqs $fastqs --transcriptome $transcriptome' \
            --yes \
            --sync ${EXTRA_OPTIONS[@]}
 
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to process the dataset"
    exit 1
fi
 
echo "[OK] Job has finished"
 
#############################################################
# Copy the results back, if requested
#############################################################
if [ "$COPY_BACK" ]; then
    RESULTS_LOCAL=$(pwd)/$(basename $RESULTS_S3)
    echo "Transferring results locally: $RESULTS_S3 -> $RESULTS_LOCAL"
    pipe storage cp $RESULTS_S3 $RESULTS_LOCAL --recursive
    if [ $? -ne 0 ]; then
        echo "[ERROR] Cannot download $RESULTS_S3 to $RESULTS_LOCAL"
    fi
    echo "[OK] Data processing results are downloaded to $RESULTS_LOCAL"
else
    echo "[OK] Data processing results are available in the S3 working directory: $RESULTS_S3"
fi
```

To launch the data processing, the script above can be launched using the following command:

```bash
# Get the "tiny" dataset (or use your own data)
cd ~
wget "https://cloud-pipeline-oss-builds.s3.amazonaws.com/tools/cellranger/data/tiny-fastq/tiny-fastq.tgz"
tar -zxvf tiny-fastq.tgz
 
 
# Run the data processing
# It is assumed that cellranger.sh is stored in ~/cellranger.sh
chmod +x ~/cellranger.sh
./cellranger.sh --fastqs ~/tiny-fastq \
                --transcriptome tiny \
                --workdir s3://my_bucket/tiny-example \
                --copy-back
 
Transferring fastqs to the S3 working directory: ~/tiny-fastq -> s3://my_bucket/tiny-example/fastq/tiny-fastq/
Launch job with parameters:
fastqs:        s3://my_bucket/tiny-example/fastq/tiny-fastq
transcriptome: s3://genome-bucket/tiny/transcriptome
results:       s3://my_bucket/tiny-example/results
Pipeline run scheduled with RunId: 5865
Pipeline run 5865 completed with status SUCCESS
 
Transferring results locally: s3://my_bucket/tiny-example/results -> ~/results
[OK] Data processing results are downloaded to ~/results
```
