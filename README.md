# YOLOv11n VisDrone 推理脚本

本项目提供一个简单的 Python 脚本，用于加载 Ultralytics 发布的 `yolov11n-visdrone.pt` 权重，对图片或视频进行推理并保存结果。

## 环境准备
1. 建议使用 Python 3.9+。
2. 安装依赖：

```bash
pip install -r requirements.txt
```

> 首次运行时，Ultralytics 会自动下载 `yolov11n-visdrone.pt` 权重到缓存目录。

## 运行示例
在本地已有图片或视频的情况下，可执行：

```bash
python run_yolov11n_visdrone.py --source path/to/your/images_or_video \
    --output runs/visdrone --name predictions --conf 0.25 --imgsz 640 --device cpu
```

常用参数说明：
- `--source`：必填，图片、视频、目录或通配符路径。
- `--weights`：可选，自定义权重路径，默认 `yolov11n-visdrone.pt`。
- `--output`/`--name`：输出目录与子目录名称，默认 `runs/visdrone/predictions`。
- `--conf`：置信度阈值，默认 0.25。
- `--imgsz`：推理分辨率，默认 640。
- `--device`：运算设备，例如 `cpu`、`0`（第一块 GPU）、`0,1`（多卡）。

推理完成后，标注结果会保存在 `runs/visdrone/<name>` 路径下（Ultralytics 默认命名）。
