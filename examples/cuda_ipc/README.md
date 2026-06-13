# CUDA IPC Image Pub/Sub

These examples publish a normal ROS-compatible `sensor_msgs/Image` while adding
an lwrclpy-only CUDA IPC side channel for subscribers on the same host.

Subscriber:

```bash
python3 examples/cuda_ipc/image_cuda_ipc_subscriber.py --open-cupy
```

Publisher:

```bash
python3 examples/cuda_ipc/image_cuda_ipc_publisher.py
```

Without CuPy/CUDA, the publisher falls back to a normal ROS-compatible Image
payload. With CuPy/CUDA, `Publisher.publish_cuda()` publishes CUDA IPC metadata
on a hidden topic and keeps the regular ROS payload enabled by default.

For lwrclpy-only throughput experiments, skip filling the regular ROS `data`
payload. The small `Image` header/metadata message is still published so the
subscriber callback fires:

```bash
python3 examples/cuda_ipc/image_cuda_ipc_publisher.py --metadata-only
```

`--metadata-only` is not useful for standard ROS 2 subscribers because they will
receive an `Image` with an empty `data` field and do not understand the hidden
CUDA IPC metadata topic.
