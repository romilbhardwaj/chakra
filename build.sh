# Build docker image
set -e
IMAGENAME=chakra
# Check if running on apple silicon
if [ "$(uname -m)" = "arm64" ]; then
    echo "Running on apple silicon"
    docker buildx build . --platform=linux/amd64 -t ${IMAGENAME} -f Dockerfile --load
else
    echo "Running on amd64"
    docker build -t ${IMAGENAME} -f Dockerfile .
fi
