/*
 * Copyright 2017-2020 EPAM Systems, Inc. (https://www.epam.com/)
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.epam.pipeline.dao.pipeline;

import com.epam.pipeline.dao.DaoHelper;
import com.epam.pipeline.entity.pipeline.StopServerlessRun;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Required;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcDaoSupport;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

public class StopServerlessRunDao extends NamedParameterJdbcDaoSupport {

    @Autowired
    private DaoHelper daoHelper;

    private String serverlessRunSequenceQuery;
    private String saveServerlessRunQuery;
    private String updateServerlessRunQuery;
    private String loadAllServerlessRunsQuery;
    private String deleteByRunIdServerlessRunQuery;

    @Transactional(propagation = Propagation.MANDATORY)
    public Long createServerlessRunId() {
        return daoHelper.createId(serverlessRunSequenceQuery);
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void createServerlessRun(final StopServerlessRun run) {
        final Long id = createServerlessRunId();
        run.setId(id);
        getNamedParameterJdbcTemplate().update(saveServerlessRunQuery,
                StopServerlessRunParameters.getParameters(run));
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void updateServerlessRun(final StopServerlessRun run) {
        getNamedParameterJdbcTemplate().update(updateServerlessRunQuery,
                StopServerlessRunParameters.getParameters(run));
    }

    public List<StopServerlessRun> loadAll() {
        return getJdbcTemplate().query(loadAllServerlessRunsQuery, StopServerlessRunParameters.getRowMapper());
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void deleteByRunId(final Long runId) {
        getJdbcTemplate().update(deleteByRunIdServerlessRunQuery, runId);
    }

    public enum StopServerlessRunParameters {
        ID,
        RUN_ID,
        LAST_UPDATE;

        static MapSqlParameterSource getParameters(final StopServerlessRun run) {
            final MapSqlParameterSource params = new MapSqlParameterSource();
            params.addValue(ID.name(), run.getId());
            params.addValue(RUN_ID.name(), run.getRunId());
            params.addValue(LAST_UPDATE.name(), run.getLastUpdate());
            return params;
        }

        static RowMapper<StopServerlessRun> getRowMapper() {
            return (rs, rowNum) -> {
                final StopServerlessRun run = new StopServerlessRun();
                run.setId(rs.getLong(ID.name()));
                run.setRunId(rs.getLong(RUN_ID.name()));
                run.setLastUpdate(rs.getTimestamp(LAST_UPDATE.name()).toLocalDateTime());
                return run;
            };
        }
    }

    @Required
    public void setServerlessRunSequenceQuery(final String serverlessRunSequenceQuery) {
        this.serverlessRunSequenceQuery = serverlessRunSequenceQuery;
    }

    @Required
    public void setLoadAllServerlessRunsQuery(final String loadAllServerlessRunsQuery) {
        this.loadAllServerlessRunsQuery = loadAllServerlessRunsQuery;
    }

    @Required
    public void setSaveServerlessRunQuery(final String saveServerlessRunQuery) {
        this.saveServerlessRunQuery = saveServerlessRunQuery;
    }

    @Required
    public void setUpdateServerlessRunQuery(final String updateServerlessRunQuery) {
        this.updateServerlessRunQuery = updateServerlessRunQuery;
    }

    @Required
    public void setDeleteByRunIdServerlessRunQuery(final String deleteByRunIdServerlessRunQuery) {
        this.deleteByRunIdServerlessRunQuery = deleteByRunIdServerlessRunQuery;
    }
}