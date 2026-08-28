namespace AntiEntropyGenerator
{
    /// <summary>
    /// Building and side-screen strings. Chinese is used as the default text so the mod
    /// displays correctly without an extra translation file.
    /// </summary>
    public static class STRINGS
    {
        public static class BUILDINGS
        {
            public static class PREFABS
            {
                public static class ANTIENTROPYGENERATOR
                {
                    public static LocString NAME = "反熵发电机";
                    public static LocString DESC =
                        "一台把“无序”抽出来发电的机器。\n\n" +
                        "左侧与上方接入液体/气体，冷却后的介质从右侧对应管道排出；底部中央输出电力。\n\n" +
                        "它把从介质中移除的热量按蒸汽发电机的效率转化为电力，同时按液体散热器/气体散热器的功率消耗电力，并把散热器的热量排到自身结构上。\n\n" +
                        "达到建造材料的过热温度后会停止工作，但不会损坏，也不会被熔化；只能通过拆除指令移除。";
                    public static LocString EFFECT =
                        "4x3\n液体输入/输出\n气体输入/输出\n电力输出\n热量转化为电力\n可调最低温度\n可调降温倍率\n材料过热后停机但不会损坏";
                    public static LocString FLAVOR = "\"把混乱装进管道，再从另一头取出秩序。\"";
                }
            }
        }

        public static class UI
        {
            public static class ANTIENTROPY
            {
                public static LocString TITLE = "反熵发电机设置";

                public static LocString MINIMUM_TEMPERATURE = "最低温度";
                public static LocString MINIMUM_TEMPERATURE_TOOLTIP =
                    "温度下限：冷却不会把介质降到这个温度以下；传入介质已经低于或等于这个温度时，直接跳过冷却。\n" +
                    "范围覆盖 0 K 到游戏最高温度 10000 K（约 -273°C 到 9727°C），因此可以为高温介质设置较高的最低温度。\n" +
                    "这是温度下限，不是温度上限：高于这个温度的介质仍然会被冷却。";

                public static LocString COOLING_MULTIPLIER = "降温倍率";
                public static LocString COOLING_MULTIPLIER_TOOLTIP =
                    "同时缩放液体/气体的降温幅度、散热器耗电、散热器发热以及由移除热量产生的电力。\n" +
                    "100% 为蒸汽涡轮机/液体冷却器/气体冷却器的标准工况；实际单次温降还会被最低温度限制。";

                public static LocString POWER_STATUS = "当前发电：{0} / {1}";
                public static LocString POWER_STATUS_TOOLTIP =
                    "按移除的热量换算出的蒸汽发电机功率。液体与气体各自最多贡献 2000 W，合计上限 4000 W。";

                public static LocString CONSUMPTION_STATUS = "散热器耗电：{0}";
                public static LocString CONSUMPTION_STATUS_TOOLTIP =
                    "液体散热器 1200 W + 气体散热器 240 W，按实际处理量缩放。";

                public static LocString NET_OUTPUT_STATUS = "净输出：{0}";
                public static LocString NET_OUTPUT_STATUS_TOOLTIP =
                    "净输出 = 当前发电 - 散热器耗电。净输出为 0 时机器仍会冷却，但不再向外供电。";

                public static LocString HEAT_STATUS = "总发热：{0}";
                public static LocString HEAT_STATUS_TOOLTIP =
                    "蒸汽发电机自身 4 kW，加上液体/气体散热器从介质中移除的热量。";

                public static LocString COOLING_STATUS = "移除热量：液体 {0}，气体 {1}";
                public static LocString COOLING_STATUS_TOOLTIP =
                    "当前每个散热器从介质中移除的热量速率。";

                public static LocString SETTINGS_STATUS = "最低温度：{0}　降温倍率：{1}";
                public static LocString SETTINGS_STATUS_TOOLTIP =
                    "可以在侧边栏中调整这两个参数。最低温度是温度下限，不会阻止高于它的介质降温。";

                public static LocString OVERHEAT_STATUS = "材料过热上限：{0}";
                public static LocString OVERHEAT_STATUS_TOOLTIP =
                    "建筑温度达到材料的过热温度时停止工作；由于建筑不可损坏，只会停机，不会受到过热伤害。";

                public static LocString NO_WIRE_STATUS = "未连接电网";
                public static LocString NO_WIRE_STATUS_TOOLTIP =
                    "反熵发电机需要接入电线才能运行。";
            }
        }
    }
}
