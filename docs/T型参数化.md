# T型：先建立本次模型，再复用计算链

历史 T/workbook.json 与 corrected_section_workbook.json 原样保留，以免丢失追溯依据。它们含固定板宽与历史 HP 行号；不应只改主尺度后直接交付。新增工具将本次模型显式写入工作副本：

```text
python scripts/check_geometry.py work/姓名/layout.json --report work/姓名/geometry_check.json
python scripts/prepare_t_model.py work/姓名/t_model.json work/姓名/model.json
python scripts/recalculate.py work/姓名/model.json work/姓名/results.json
python scripts/select_profiles.py work/姓名/model.json work/姓名/profile_candidates.json
```

格式参看 examples/t_layout.json 与 examples/t_model.example.json。**示例为合成工具数据，其压力、型材及布置不得作为真实作业的默认方案。** 从老师的本次输入建立 given；layout 中所有长度为米，full_count为全剖面数量。坐标x_from_center_m从中线向外量；wing_x_from_shell_m从外舷向内量。
v3要求schema_version=3，design_inputs中显式列舱长、材料/载荷/腐蚀假设及来源，profiles包含全部16组；完整必填字段见输入字段契约.md。旧配置缺项要迁移，不从旧船偷偷补默认值。

## 几何

直线梁拱假设：距外舷 b 的点高度 `D + f*b/(B/2)`；距中线 x 的点高度 `D + f*(1-x/(B/2))`。内舷侧的位置是前一种 b，不能把两个坐标混用。例如 B=27、D=15.5、f=0.54、b=2 时高度为15.58 m。

新草稿把平底、舭弧、垂直舷侧、内舷侧分别按本次声明的板带比例分配；换主尺度后每组仍闭合，不再用 `2000-F1`、`2000-G1` 把相邻余量逼成负值。板带比例只是选定布置；改船后仍应重新审查实际板宽、龙骨/舷顶列板要求和制造条件。并非板带必须统一2000 mm，也不能简单钳制负值为0。

check_geometry分别检查四段闭合、所有板宽为正、内舷侧接甲板高度、实际末端间距、构件数量和支承跨度；可同时核对profile_bindings中选型与等效梁的面积/惯性矩/重心。它检查的是声明模型，不能冒充读取最终DWG；CAD仍需导出实体坐标或在AutoCAD中实测并与声明比较。输入只给总周长不足以检查接缝位置。

当前草稿延用样本拓扑：7段平底、2段舭弧、9段垂直舷侧、7段内舷侧、3个平台、至多14对货舱甲板纵骨、2对双舷侧甲板纵骨。超出时中止并要求扩展计算行和图纸；不能悄悄截断构件。输出是待设计审查的草稿，不是完整作业。

## 甲板压力分区

在deck_cases.cargo和deck_cases.wing分别列出工况，每项有condition、inside_kpa、outside_kpa、basis。两个压力必须属于同一工况、同一部位高度与同一方向约定；不同方向分别分析。新表`Параметры модели`按每行差压绝对值计算，再分别取两区包络，独立连接Балки!E22与E23。工况遗漏不是取MAX能弥补的。
schema3还要求inside_kind与combination_mode；有利抵消须有两侧匹配的case_id、point_id、phase_id、draft_m、z_m及combination_basis。包络内压不能直接抵消一个波压最大值。未采用抵消时明确no_counterpressure且outside=0，另审查外压控制组合，详见字段契约。

这些数值必须来自本次已推导的压力计算，basis写明来源/算式/控制位置，不能输入历史结果或编造数值。改变吃水、液位、甲板高度、密度或动载时必须重新生成这些工况；不自动假设两个区相同。若两区最终最大值恰好相同，可以相同，但需分别有计算依据。历史Нагрузки!B85是混合包络，不宜未经说明同时作为两个分区的设计值。

## 型材及等效梁

profiles中各组名称对应data/hp_catalog.json；工具将同一记录的h、s、A、y、I放入组合截面，并让等效梁直接引用该组的截面性质。新名字不会再配上旧HP行号。图纸也应消费同一份profiles与坐标。
CL-F1～4也从同一身份记录生成附加构件页的组合截面，不再保留旧HP硬编码行。立柱腹板最小厚度须在design_inputs.cl_web_min_mm明确给出依据；没有依据时不能宣布16组约束全部通过。

select_profiles枚举目录全部候选，按本次W要求与最小腹板厚度过滤，按单位长度质量排序并留下候选记录；不只试几个型号。它只证明该目录、这些约束下的最轻，不代替剪切、屈曲、连接和强支承构件校核。采用候选后更新t_model.json并重新prepare/recalculate，更新CAD和全部依赖，不直接在输出表里只改型号文字。
该入口现覆盖主表12组及CL-F4组，共16组；缺少CL腹板要求时返回待补而非默认通过。使用check_t_assignment.py检查实际表，不能以选型候选报告代替最终成品校核。

组合截面以带板中面为z=0，带板重心为0，型材重心为 `y0+t/2`。惯性矩中的带板平行轴项应为 `Ap*e²`，不能写成 `Ap*(e-t/2)²`。同一坐标系贯穿重心、惯性矩和两侧W。

## 尚需完成的设计工作

压力分区工具目前连接甲板两组骨材；甲板板带、内底/内舷侧、其他荷载控制点也须按实际分区审查并更新，不能因两个单元格分开就宣称整套荷载模型已完成。模板的屈曲、支承、腐蚀、跨度和板厚等其余公式仍需按当年课程要求适配。平台/中纵舱壁等附加构件必须核实是否计入总纵有效截面，不能仅因图上存在就自动全额加入。
