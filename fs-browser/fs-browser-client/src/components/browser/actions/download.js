import React from 'react';
import {inject, observer} from 'mobx-react';
import Icon from '../../shared/icon';
import styles from '../browser.css';

function download(
  {
    disabled,
    item,
    messages,
    taskManager,
    callback,
  },
) {
  if (!item.downloadable) {
    return null;
  }
  const [downloadTask] = taskManager.getTasksByPath(item.path)
    .filter(i => i.item.type === 'download');
  const isDownloading = downloadTask && downloadTask.isRunning;
  const onClick = async (e) => {
    e.stopPropagation();
    const hide = messages.loading('Initializing download process...', 0);
    const {error, value} = await taskManager.download(item.path);
    hide();
    if (error) {
      messages.error(error, 5);
    } else if (callback) {
      callback(item, taskManager.getTaskById(value.task));
    }
  };
  if (isDownloading) {
    return (
      <span
        className={styles.action}
      >
        <Icon
          type="loading"
          width={20}
        />
      </span>
    );
  }
  return (
    <span
      className={styles.action}
    >
      <Icon
        disabled={disabled}
        type="download"
        onClick={onClick}
      />
    </span>
  );
}

export default inject('messages', 'taskManager')(observer(download));
