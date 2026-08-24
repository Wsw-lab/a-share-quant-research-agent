# GitHub Submission Checklist

本清单检查公开树是否忠实于 `research_snapshot_v1` 与 `INSUFFICIENT_EVIDENCE` 边界；它不生成“展示就绪”或交易批准分数。

## 应保留

- `README.md`、三份边界文档与 `docs/` 设计记录；
- `src/a_share_quant_agent/` 当前可导入模块；
- `examples/run_demo.py` 与 checked-in strategy spec；
- `tests/` 和合成 QData snapshot fixture；
- `data_assets/templates/` 字段模板；
- 只读 `.github/workflows/ci.yml` 及固定 CI 依赖文件。

## 不应提交

- 运行时报告、receipt、snapshot、缓存、构建目录或 editable-install 元数据；
- 带本机绝对路径的清单；
- 凭据、token、私有数据或未授权市场数据；
- 无法由当前 checkout 重建的策略指标；
- 声称券商、实盘交易、生产部署或远端 CI 成功的文字，除非另有可核验证据。

## 本地最终检查

```bash
export PYTHONPATH=src
python3 -m unittest -v tests.test_public_surface_contract
python3 -m unittest discover -s tests -p 'test_*.py'
python3 examples/run_demo.py
git diff --check
```

严格实验双跑、receipt verify 和 tamper rejection 的完整命令由 [README 唯一绿色路径](README.md#全新-checkout-的唯一离线绿色路径)及 CI 定义。其公开 fixture 只有 2 个标的、3 个交易会话，结论必须保持 `INSUFFICIENT_EVIDENCE`。

在 GitHub 页面上确认真实 Actions run 之前，只能说工作流已配置并经本地静态检查，不能说托管 CI 已通过。许可证仍由仓库所有者决定；不要代为添加。
