CREATE SEQUENCE PIPELINE.S_METADATA_CLASS START WITH 1 INCREMENT BY 1;
CREATE SEQUENCE PIPELINE.S_METADATA_ENTITY START WITH 1 INCREMENT BY 1;

CREATE TABLE IF NOT EXISTS PIPELINE.METADATA_ENTITY_CLASS (
    CLASS_ID    BIGINT  NOT	NULL    PRIMARY KEY,
    CLASS_NAME  TEXT    NOT NULL,
    CONSTRAINT  UNIQUE_ME_1 UNIQUE(CLASS_NAME)
);

CREATE TABLE IF NOT EXISTS PIPELINE.METADATA_ENTITY (
    ENTITY_ID   BIGINT  NOT NULL    PRIMARY KEY,
    CLASS_ID    BIGINT  NOT	NULL,
    PARENT_ID   BIGINT,
    ENTITY_NAME VARCHAR(100),
    EXTERNAL_ID TEXT,
    DATA    JSONB,
    CONSTRAINT  class_id_fkey   FOREIGN KEY (CLASS_ID)  REFERENCES PIPELINE.METADATA_ENTITY_CLASS (CLASS_ID),
    CONSTRAINT  parent_id_fkey  FOREIGN KEY (PARENT_ID) REFERENCES PIPELINE.FOLDER (FOLDER_ID),
    CONSTRAINT  UNIQUE_ME_2 UNIQUE(CLASS_ID,PARENT_ID,ENTITY_NAME)
);

CREATE INDEX metadata_entity_index_jsonb ON pipeline.metadata_entity USING GIN (data);
CREATE INDEX metadata_entity_index ON pipeline.metadata_entity (entity_id, class_id);