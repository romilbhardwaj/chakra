# Pushes the docker image to the Google Cloud Registry

REPO=us-docker.pkg.dev/romil-sky-exp/chakra/chakra:latest
docker tag chakra $REPO
docker push $REPO