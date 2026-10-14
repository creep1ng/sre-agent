FROM public.ecr.aws/aws-cli/aws-cli:2.36.49@sha256:b47eaab8827b1015999fb6a0bc392c482f07a21a445ae269f8934473e714a1d1 AS awscli
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
COPY --from=awscli /usr/local/aws-cli /usr/local/aws-cli
RUN ln -s /usr/local/aws-cli/v2/current/bin/aws /usr/local/bin/aws
ENV AWS_EC2_METADATA_DISABLED=true AWS_PAGER=""
WORKDIR /owner
ENTRYPOINT ["python"]
