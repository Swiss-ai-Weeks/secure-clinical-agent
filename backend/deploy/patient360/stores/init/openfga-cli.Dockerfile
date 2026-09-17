# openfga-init image: the official openfga/cli image is distroless (no shell), so the
# fga binary is copied into Alpine to run stores/init/openfga.sh with sh and jq.
# The binary lives at /fga upstream (.goreleaser.Dockerfile: COPY .../fga /fga).
FROM openfga/cli:v0.7.20 AS cli

FROM public.ecr.aws/docker/library/alpine:3.20
RUN apk add --no-cache jq
COPY --from=cli /fga /usr/local/bin/fga
ENTRYPOINT ["/bin/sh"]
