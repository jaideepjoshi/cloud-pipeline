CREATE SEQUENCE IF NOT  EXISTS pipeline.S_DOCKER_REGISTRY START WITH 1 INCREMENT BY 1;
CREATE TABLE IF NOT EXISTS PIPELINE.DOCKER_REGISTRY (
  ID   BIGINT    NOT NULL PRIMARY KEY,
  PATH TEXT      NOT NULL,
  DESCRIPTION   TEXT
);
