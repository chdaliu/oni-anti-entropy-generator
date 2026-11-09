using System.Collections.Generic;
using KSerialization;
using UnityEngine;

namespace AntiEntropyGenerator
{
    /// <summary>
    /// Core logic for the Anti-Entropy Generator.
    ///
    /// It cools liquid/gas from the input buffers, moves the cooled medium to the matching
    /// output buffers, converts the removed heat into power, deducts the cooler power from
    /// that output, and dumps the removed heat into the building's own structure temperature.
    ///
    /// The minimum temperature is a floor: media above it are cooled, media at or below it
    /// are skipped, and cooling never takes a medium below the floor. It is not an upper
    /// temperature cap.
    /// </summary>
    [SerializationConfig(MemberSerialization.OptIn)]
    public sealed class AntiEntropyGeneratorCore : Generator, IMultiSliderControl, IGameObjectEffectDescriptor
    {
        public const float MAX_WATTAGE = 4000f;
        public const float WATTAGE_PER_MEDIUM = 2000f;
        public const float LIQUID_COOLER_WATTS = 1200f;
        public const float GAS_COOLER_WATTS = 240f;
        public const float LIQUID_FLOW_KG_S = 10f;
        public const float GAS_FLOW_KG_S = 1f;
        public const float BASE_DELTA_C = 14f;
        public const float STEAM_TURBINE_SELF_HEAT_KW = 4f;
        public const float MAX_COOLING_MULTIPLIER = 3f;

        public const string TITLE_KEY = "STRINGS.UI.ANTIENTROPY.TITLE";
        public const string MINIMUM_TEMPERATURE_KEY = "STRINGS.UI.ANTIENTROPY.MINIMUM_TEMPERATURE";
        public const string COOLING_MULTIPLIER_KEY = "STRINGS.UI.ANTIENTROPY.COOLING_MULTIPLIER";

        private const string HEAT_SOURCE = "AntiEntropyGeneratorCooling";

        [Serialize]
        private float minimumTemperatureKelvin = 293.15f;

        [Serialize]
        private float coolingMultiplier = 1f;

        // Assigned on the prefab by AntiEntropyGeneratorConfig.ConfigureBuildingTemplate.
        public Storage liquidInputStorage;
        public Storage liquidOutputStorage;
        public Storage gasInputStorage;
        public Storage gasOutputStorage;

        private static readonly Operational.Flag tooHotFlag =
            new Operational.Flag("AntiEntropyGeneratorTooHot", Operational.Flag.Type.Requirement);

        private PrimaryElement primaryElement;
        private Overheatable overheatable;
        private EnergyConsumerSelfSustaining gridConsumer;
        private HandleVector<int>.Handle structureTemperature;
        private ISliderControl[] sliders;
        private bool tooHotLatched;
        private bool gridPowerStarved;

        private float lastGrossWatts;
        private float lastConsumptionWatts;
        private float lastNetWatts;
        private float lastGridDrawWatts;
        private float lastHeatKw;
        private float lastLiquidHeatKw;
        private float lastGasHeatKw;

        public float MinimumTemperatureCelsius => minimumTemperatureKelvin - 273.15f;
        public float CoolingMultiplier => coolingMultiplier;

        protected override void OnSpawn()
        {
            base.OnSpawn();
            primaryElement = GetComponent<PrimaryElement>();
            overheatable = GetComponent<Overheatable>();
            gridConsumer = GetComponent<EnergyConsumerSelfSustaining>();
            if (gridConsumer != null)
            {
                // Start self-sustained so the generator can bootstrap on an empty circuit
                // when its own output covers the cooler load. Process() switches this off
                // when external power is needed.
                gridConsumer.SetSustained(true);
                gridConsumer.BaseWattageRating = 0f;
                gridConsumer.UpdatePoweredStatus();
            }

            structureTemperature = GameComps.StructureTemperatures.GetHandle(gameObject);
            sliders = new ISliderControl[]
            {
                new MinimumTemperatureSlider(this),
                new CoolingMultiplierSlider(this)
            };
        }

        public override void EnergySim200ms(float dt)
        {
            base.EnergySim200ms(dt);

            UpdateOverheatState();

            // Match vanilla generators: stop when the power output is not connected to a wire.
            operational.SetFlag(wireConnectedFlag, CircuitID != ushort.MaxValue);

            if (!operational.IsOperational)
            {
                operational.SetActive(false);

                // If the previous tick needed grid power and did not get it, clear any
                // leftover joules so the machine cannot quietly self-power the deficit.
                gridPowerStarved =
                    gridConsumer != null
                    && lastGridDrawWatts > 0.01f
                    && !gridConsumer.IsExternallyPowered;

                if (gridPowerStarved)
                {
                    ConsumeEnergy(JoulesAvailable);
                }

                // Keep the last grid-draw value visible while starved, so the descriptor
                // explains why the building stopped.
                ResetLastValues(keepGridDraw: gridPowerStarved);
                return;
            }

            Process(dt);
        }

        private void UpdateOverheatState()
        {
            float limit = overheatable != null ? overheatable.OverheatTemperature : 10000f;
            float temperature = primaryElement != null ? primaryElement.Temperature : 0f;

            if (temperature >= limit - 0.01f)
            {
                tooHotLatched = true;
            }
            else if (tooHotLatched && temperature < limit - 10f)
            {
                // 10 C hysteresis prevents rapid on/off toggling at the overheat limit.
                tooHotLatched = false;
            }

            operational.SetFlag(tooHotFlag, !tooHotLatched);
        }

        private void ResetLastValues(bool keepGridDraw = false)
        {
            lastGrossWatts = 0f;
            lastConsumptionWatts = 0f;
            lastNetWatts = 0f;
            if (!keepGridDraw)
            {
                lastGridDrawWatts = 0f;
            }

            lastHeatKw = 0f;
            lastLiquidHeatKw = 0f;
            lastGasHeatKw = 0f;
        }

        private void Process(float dt)
        {
            gridPowerStarved = false;
            float liquidHeat = 0f;
            float gasHeat = 0f;
            float liquidHeatFraction = 0f;
            float gasHeatFraction = 0f;
            float liquidFlowFraction = 0f;
            float gasFlowFraction = 0f;
            bool anyCooling = false;

            ProcessMedium(
                liquidInputStorage,
                liquidOutputStorage,
                ConduitType.Liquid,
                LIQUID_FLOW_KG_S,
                ref liquidHeat,
                ref liquidHeatFraction,
                ref liquidFlowFraction,
                ref anyCooling,
                dt);

            ProcessMedium(
                gasInputStorage,
                gasOutputStorage,
                ConduitType.Gas,
                GAS_FLOW_KG_S,
                ref gasHeat,
                ref gasHeatFraction,
                ref gasFlowFraction,
                ref anyCooling,
                dt);

            // Generation follows the heat actually removed. Cooler power follows the volume
            // actually processed: running near the minimum temperature can therefore cost more
            // than the machine generates, and the deficit is drawn from the grid.
            float gross = Mathf.Min(
                MAX_WATTAGE,
                WATTAGE_PER_MEDIUM * (liquidHeatFraction + gasHeatFraction));
            float consumption =
                LIQUID_COOLER_WATTS * liquidFlowFraction +
                GAS_COOLER_WATTS * gasFlowFraction;
            float net = Mathf.Max(0f, gross - consumption);
            float gridDraw = Mathf.Max(0f, consumption - gross);
            float coolerHeat = liquidHeat + gasHeat;

            operational.SetActive(anyCooling);

            // Feed the full gross output into the circuit. The hidden EnergyConsumer below
            // draws the cooler load back out: when gross >= load the surplus stays available
            // to the grid, and when gross < load the deficit is taken from batteries or other
            // generators. If nothing can cover the deficit the consumer reports Unpowered,
            // which makes the building non-operational until the grid can supply it.
            if (gridConsumer != null)
            {
                gridConsumer.BaseWattageRating = consumption;
                gridConsumer.SetSustained(gridDraw <= 0.01f);
                gridConsumer.UpdatePoweredStatus();
            }

            if (gross > 0f && dt > 0f)
            {
                GenerateJoules(gross * dt);
            }

            // Heat removed by the coolers is added to the building itself. The 4 kW steam
            // turbine self-heat is added separately by BuildingDef.SelfHeatKilowattsWhenActive
            // while the building is active.
            if (coolerHeat > 0.0001f && dt > 0f && structureTemperature.IsValid())
            {
                GameComps.StructureTemperatures.ProduceEnergy(
                    structureTemperature,
                    coolerHeat * dt,
                    HEAT_SOURCE,
                    dt);
            }

            lastGrossWatts = gross;
            lastConsumptionWatts = consumption;
            lastNetWatts = net;
            lastGridDrawWatts = gridDraw;
            lastLiquidHeatKw = liquidHeat;
            lastGasHeatKw = gasHeat;
            lastHeatKw = anyCooling ? coolerHeat + STEAM_TURBINE_SELF_HEAT_KW : 0f;
        }

        private void ProcessMedium(
            Storage input,
            Storage output,
            ConduitType type,
            float nominalFlow,
            ref float heat,
            ref float heatFraction,
            ref float flowFraction,
            ref bool anyCooling,
            float dt)
        {
            if (input == null || output == null || input.items.Count == 0 || dt <= 0f)
            {
                return;
            }

            float remaining = nominalFlow * dt;
            int guard = 0;

            while (remaining > 0.0001f && input.items.Count > 0 && guard++ < 128)
            {
                GameObject item = input.items[0];
                if (item == null)
                {
                    input.items.RemoveAt(0);
                    continue;
                }

                PrimaryElement element = item.GetComponent<PrimaryElement>();
                if (element == null || element.Mass <= 0f)
                {
                    if (element != null)
                    {
                        element.KeepZeroMassObject = false;
                    }

                    input.ConsumeIgnoringDisease(item);
                    continue;
                }

                float amount = Mathf.Min(element.Mass, remaining);
                amount = Mathf.Min(amount, output.RemainingCapacity());
                if (amount <= 0.0001f)
                {
                    break;
                }

                flowFraction += amount / (nominalFlow * dt);

                float temperature = element.Temperature;

                // The minimum temperature is a floor. A medium above it is cooled by the
                // configured delta, but never below the floor; a medium at or below the
                // floor is simply passed through.
                float delta = 0f;
                if (coolingMultiplier > 0f && temperature > minimumTemperatureKelvin)
                {
                    delta = Mathf.Min(
                        BASE_DELTA_C * coolingMultiplier,
                        temperature - minimumTemperatureKelvin);
                }

                if (delta < 0f)
                {
                    delta = 0f;
                }

                float specificHeat = element.Element != null
                    ? element.Element.specificHeatCapacity
                    : 0f;

                float removedHeat = 0f;
                if (delta > 0.0001f && specificHeat > 0f)
                {
                    removedHeat = amount * specificHeat * delta;
                    heat += removedHeat;
                    anyCooling = true;

                    float referenceHeat = nominalFlow * specificHeat * BASE_DELTA_C;
                    if (referenceHeat > 0.0001f)
                    {
                        heatFraction += removedHeat / referenceHeat;
                    }
                }

                SimHashes elementId = element.ElementID;
                byte diseaseIdx = element.DiseaseIdx;
                int diseaseCount = 0;
                if (element.Mass > 0f)
                {
                    diseaseCount = Mathf.RoundToInt(element.DiseaseCount * (amount / element.Mass));
                }

                element.Mass -= amount;
                if (diseaseCount != 0)
                {
                    element.ModifyDiseaseCount(-diseaseCount, "AntiEntropyGenerator.Cool");
                }

                if (element.Mass <= 0.0001f)
                {
                    element.KeepZeroMassObject = false;
                    input.ConsumeIgnoringDisease(item);
                }

                float outputTemperature = temperature - delta;
                if (type == ConduitType.Liquid)
                {
                    output.AddLiquid(
                        elementId,
                        amount,
                        outputTemperature,
                        diseaseIdx,
                        diseaseCount,
                        keep_zero_mass: true);
                }
                else
                {
                    output.AddGasChunk(
                        elementId,
                        amount,
                        outputTemperature,
                        diseaseIdx,
                        diseaseCount,
                        keep_zero_mass: true);
                }

                remaining -= amount;
            }

            flowFraction = Mathf.Clamp01(flowFraction);
        }

        public List<Descriptor> GetDescriptors(GameObject go)
        {
            List<Descriptor> descriptors = new List<Descriptor>();

            descriptors.Add(new Descriptor(
                string.Format(STRINGS.UI.ANTIENTROPY.POWER_STATUS,
                    GameUtil.GetFormattedWattage(lastGrossWatts),
                    GameUtil.GetFormattedWattage(MAX_WATTAGE)),
                STRINGS.UI.ANTIENTROPY.POWER_STATUS_TOOLTIP));

            descriptors.Add(new Descriptor(
                string.Format(STRINGS.UI.ANTIENTROPY.CONSUMPTION_STATUS,
                    GameUtil.GetFormattedWattage(lastConsumptionWatts)),
                STRINGS.UI.ANTIENTROPY.CONSUMPTION_STATUS_TOOLTIP));

            descriptors.Add(new Descriptor(
                string.Format(STRINGS.UI.ANTIENTROPY.NET_OUTPUT_STATUS,
                    GameUtil.GetFormattedWattage(lastNetWatts)),
                STRINGS.UI.ANTIENTROPY.NET_OUTPUT_STATUS_TOOLTIP));

            if (lastGridDrawWatts > 0.01f)
            {
                bool starved = gridPowerStarved
                    || (gridConsumer != null && !gridConsumer.IsPowered);
                descriptors.Add(new Descriptor(
                    string.Format(
                        starved
                            ? STRINGS.UI.ANTIENTROPY.GRID_STARVED_STATUS
                            : STRINGS.UI.ANTIENTROPY.GRID_DRAW_STATUS,
                        GameUtil.GetFormattedWattage(lastGridDrawWatts)),
                    starved
                        ? STRINGS.UI.ANTIENTROPY.GRID_STARVED_STATUS_TOOLTIP
                        : STRINGS.UI.ANTIENTROPY.GRID_DRAW_STATUS_TOOLTIP));
            }

            descriptors.Add(new Descriptor(
                string.Format(STRINGS.UI.ANTIENTROPY.HEAT_STATUS,
                    GameUtil.GetFormattedHeatEnergyRate(lastHeatKw * 1000f)),
                STRINGS.UI.ANTIENTROPY.HEAT_STATUS_TOOLTIP));

            descriptors.Add(new Descriptor(
                string.Format(STRINGS.UI.ANTIENTROPY.COOLING_STATUS,
                    GameUtil.GetFormattedHeatEnergyRate(lastLiquidHeatKw * 1000f),
                    GameUtil.GetFormattedHeatEnergyRate(lastGasHeatKw * 1000f)),
                STRINGS.UI.ANTIENTROPY.COOLING_STATUS_TOOLTIP));

            descriptors.Add(new Descriptor(
                string.Format(STRINGS.UI.ANTIENTROPY.SETTINGS_STATUS,
                    GameUtil.GetFormattedTemperature(minimumTemperatureKelvin),
                    GameUtil.GetFormattedPercent(coolingMultiplier * 100f)),
                STRINGS.UI.ANTIENTROPY.SETTINGS_STATUS_TOOLTIP));

            float overheatTemperature = overheatable != null ? overheatable.OverheatTemperature : 10000f;
            descriptors.Add(new Descriptor(
                string.Format(STRINGS.UI.ANTIENTROPY.OVERHEAT_STATUS,
                    GameUtil.GetFormattedTemperature(overheatTemperature)),
                STRINGS.UI.ANTIENTROPY.OVERHEAT_STATUS_TOOLTIP));

            return descriptors;
        }

        public string SidescreenTitleKey => TITLE_KEY;

        public ISliderControl[] sliderControls =>
            sliders ?? (sliders = new ISliderControl[]
            {
                new MinimumTemperatureSlider(this),
                new CoolingMultiplierSlider(this)
            });

        public bool SidescreenEnabled()
        {
            return true;
        }

        private void SetMinimumTemperatureCelsius(float celsius)
        {
            if (float.IsNaN(celsius) || float.IsInfinity(celsius))
            {
                return;
            }

            minimumTemperatureKelvin = Mathf.Clamp(
                celsius + 273.15f,
                0f,
                Sim.MaxTemperature);
        }

        private void SetCoolingMultiplierPercent(float percent)
        {
            if (float.IsNaN(percent) || float.IsInfinity(percent))
            {
                return;
            }

            coolingMultiplier = Mathf.Clamp(percent / 100f, 0f, MAX_COOLING_MULTIPLIER);
        }

        private sealed class MinimumTemperatureSlider : ISliderControl
        {
            private readonly AntiEntropyGeneratorCore core;

            public MinimumTemperatureSlider(AntiEntropyGeneratorCore core)
            {
                this.core = core;
            }

            public string SliderTitleKey => MINIMUM_TEMPERATURE_KEY;
            public string SliderUnits => "°C";

            public int SliderDecimalPlaces(int index) => 0;

            // 0 K to Sim.MaxTemperature (10000 K), expressed in Celsius.
            public float GetSliderMin(int index) => 0f - 273.15f;
            public float GetSliderMax(int index) => Sim.MaxTemperature - 273.15f;
            public float GetSliderValue(int index) => core.MinimumTemperatureCelsius;
            public void SetSliderValue(float value, int index) => core.SetMinimumTemperatureCelsius(value);

            public string GetSliderTooltipKey(int index) => "";
            public string GetSliderTooltip(int index) =>
                STRINGS.UI.ANTIENTROPY.MINIMUM_TEMPERATURE_TOOLTIP.ToString();
        }

        private sealed class CoolingMultiplierSlider : ISliderControl
        {
            private readonly AntiEntropyGeneratorCore core;

            public CoolingMultiplierSlider(AntiEntropyGeneratorCore core)
            {
                this.core = core;
            }

            public string SliderTitleKey => COOLING_MULTIPLIER_KEY;
            public string SliderUnits => "%";

            public int SliderDecimalPlaces(int index) => 0;
            public float GetSliderMin(int index) => 0f;
            public float GetSliderMax(int index) => MAX_COOLING_MULTIPLIER * 100f;
            public float GetSliderValue(int index) => core.CoolingMultiplier * 100f;
            public void SetSliderValue(float value, int index) => core.SetCoolingMultiplierPercent(value);

            public string GetSliderTooltipKey(int index) => "";
            public string GetSliderTooltip(int index) =>
                STRINGS.UI.ANTIENTROPY.COOLING_MULTIPLIER_TOOLTIP.ToString();
        }
    }
}
