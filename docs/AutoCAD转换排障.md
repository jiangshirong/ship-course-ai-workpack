# DWG转换失败时

命令：`python scripts/dxf_to_dwg.py work/姓名/project.dxf outputs/姓名/姓名_проект.dwg`。源文件必须存在，输出文件不能已存在。脚本只关闭自己打开的文档。

1. 查看错误阶段：connect、open DXF、SaveAs DWG或close。确认本机安装可用AutoCAD、没有等待交互的模态对话框，当前用户有输出目录写入权限。
2. 若COM注册号不匹配，用`--progid`指定本机真实安装的AutoCAD版本；不要照抄整理者的版本号。未注册/未安装不是改文件后缀能解决的。
3. 若出现`AttributeError: Open.SaveAs`、`<unknown>.Count`等返回对象包装问题，本脚本已改用显式IDispatch调用已知属性/方法，以减少pywin32类型信息错误。不要改为保存ActiveDocument，用户可能切到了其他图纸。
4. 若仍失败，可在AutoCAD中手动打开本次DXF，以“另存为”创建新DWG，记录转换为人工完成，再打开该DWG核对。已安装且可用的AutoCAD MCP也可操作；这不是工作包依赖。
5. 若提示自己打开的文档无法关闭，只手动关闭该转换文档；不强制结束AutoCAD、不关闭用户其他文件、不删除仍在使用的锁文件。

转换完成要核实文件格式、实体和实际外观。不能以DXF审计“0 errors”替代原生DWG检查。自动保存失败时也不能冒充已经成功交付。
