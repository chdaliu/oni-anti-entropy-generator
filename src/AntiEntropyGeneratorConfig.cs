using System.Collections.Generic;
using TUNING;
using UnityEngine;

namespace AntiEntropyGenerator
{
    /// <summary>
    /// 4x3 Anti-Entropy Generator. All four fluid ports are provided through
    /// ISecondaryInput/ISecondaryOutput, so one building can expose liquid input/output and
    /// gas input/output at the same time. Power has a single output port at the bottom.
    /// </summary>
    public sealed class AntiEntropyGeneratorConfig : IBuildingConfig
    {
        public const string ID = "AntiEntropyGenerator";
        public const string ANIM = "anti_entropy_generator_kanim";

        public const int WIDTH = 4;
        public const int HEIGHT = 3;

        // Do not gate the building behind any DLC. It must load in vanilla, single-DLC,
        // partial-DLC and mixed-DLC saves.
        public override string[] GetRequiredDlcIds()
        {
            return new string[0];
        }

        public override string[] GetForbiddenDlcIds()
        {
            return new string[0];
        }

        public override BuildingDef CreateBuildingDef()
        {
            BuildingDef def = BuildingTemplates.CreateBuildingDef(
                ID,
                WIDTH,
                HEIGHT,
                ANIM,
                100,
                60f,
                new float[] { 1200f },
                new string[] { "RefinedMetal" },
                1600f,
                BuildLocationRule.OnFloor,
                TUNING.BUILDINGS.DECOR.NONE,
                TUNING.NOISE_POLLUTION.NONE,
                1f);

            // Power: one output port in the middle of the bottom row.
            def.GeneratorWattageRating = AntiEntropyGeneratorCore.MAX_WATTAGE;
            def.GeneratorBaseCapacity = AntiEntropyGeneratorCore.MAX_WATTAGE;
            def.RequiresPowerOutput = true;
            def.PowerOutputOffset = new CellOffset(1, 0);
            def.EnergyConsumptionWhenActive = 0f;

            // Steam-turbine self heat. The cooler heat is added to the structure at runtime.
            def.SelfHeatKilowattsWhenActive = AntiEntropyGeneratorCore.STEAM_TURBINE_SELF_HEAT_KW;
            def.ExhaustKilowattsWhenActive = 0f;

            // Stop at the material overheat temperature, but never take damage.
            def.Overheatable = true;
            def.OverheatTemperature = 348.15f; // 75 C base; steel +200 => 275 C
            def.FatalHot = 1273.15f;
            def.Invincible = true;
            def.Breakable = false;
            def.Repairable = false;
            def.Floodable = false;
            def.Entombable = true;

            // Participate in structure temperature simulation so cooler heat can be added
            // to the building and clamped by its overheat limit.
            def.UseStructureTemperature = true;
            def.ThermalConductivity = 1f;

            def.ObjectLayer = ObjectLayer.Building;
            def.SceneLayer = Grid.SceneLayer.Building;
            def.ContinuouslyCheckFoundation = true;
            def.AudioCategory = "Metal";
            def.AudioSize = "large";
            def.PermittedRotations = PermittedRotations.Unrotatable;
            def.DefaultAnimState = "idle";
            def.BaseTimeUntilRepair = -1f;
            def.ViewMode = OverlayModes.Power.ID;

            def.AddSearchTerms(global::STRINGS.SEARCH_TERMS.POWER);
            def.AddSearchTerms(global::STRINGS.SEARCH_TERMS.GENERATOR);
            def.AddSearchTerms(global::STRINGS.SEARCH_TERMS.STEAM);

            return def;
        }

        public override void ConfigureBuildingTemplate(GameObject go, Tag prefab_tag)
        {
            go.GetComponent<KPrefabID>().AddTag(RoomConstraints.ConstraintTags.IndustrialMachinery);
            go.GetComponent<KPrefabID>().AddTag(RoomConstraints.ConstraintTags.PowerBuilding);
            go.GetComponent<KPrefabID>().AddTag(RoomConstraints.ConstraintTags.GeneratorType);
            go.GetComponent<KPrefabID>().AddTag(RoomConstraints.ConstraintTags.HeavyDutyGeneratorType);

            // Four independent buffers: liquid in/out and gas in/out.
            Storage liquidIn = AddStorage(go, 100f, STORAGEFILTERS.LIQUIDS);
            Storage liquidOut = AddStorage(go, 100f, STORAGEFILTERS.LIQUIDS);
            Storage gasIn = AddStorage(go, 10f, STORAGEFILTERS.GASES);
            Storage gasOut = AddStorage(go, 10f, STORAGEFILTERS.GASES);

            // Add port managers before consumers/dispensers to keep OnSpawn order stable.
            go.AddOrGet<AntiEntropyInputPorts>();
            go.AddOrGet<AntiEntropyOutputPorts>();

            ConduitConsumer liquidConsumer = go.AddComponent<ConduitConsumer>();
            ConfigureConsumer(
                liquidConsumer,
                ConduitType.Liquid,
                liquidIn,
                AntiEntropyGeneratorCore.LIQUID_FLOW_KG_S,
                useSecondary: true);

            ConduitConsumer gasConsumer = go.AddComponent<ConduitConsumer>();
            ConfigureConsumer(
                gasConsumer,
                ConduitType.Gas,
                gasIn,
                AntiEntropyGeneratorCore.GAS_FLOW_KG_S,
                useSecondary: true);

            ConduitDispenser liquidDispenser = go.AddComponent<ConduitDispenser>();
            ConfigureDispenser(liquidDispenser, ConduitType.Liquid, liquidOut, useSecondary: true);

            ConduitDispenser gasDispenser = go.AddComponent<ConduitDispenser>();
            ConfigureDispenser(gasDispenser, ConduitType.Gas, gasOut, useSecondary: true);

            AntiEntropyGeneratorCore core = go.AddOrGet<AntiEntropyGeneratorCore>();
            core.liquidInputStorage = liquidIn;
            core.liquidOutputStorage = liquidOut;
            core.gasInputStorage = gasIn;
            core.gasOutputStorage = gasOut;
        }

        public override void DoPostConfigureComplete(GameObject go)
        {
            go.AddOrGet<AntiEntropyAnimator>();

            // Keep the standard prioritizable entry for generator-like buildings, even though
            // this building has no duplicant-operated errands.
            Prioritizable.AddRef(go);
        }

        private static Storage AddStorage(GameObject go, float capacity, List<Tag> filters)
        {
            Storage storage = go.AddComponent<Storage>();
            storage.capacityKg = capacity;
            storage.showInUI = false;
            storage.showDescriptor = false;
            storage.showCapacityStatusItem = false;
            storage.showCapacityAsMainStatus = false;
            storage.allowItemRemoval = true;
            storage.storageFilters = filters;
            storage.SetDefaultStoredItemModifiers(Storage.StandardSealedStorage);
            return storage;
        }

        private static void ConfigureConsumer(
            ConduitConsumer consumer,
            ConduitType type,
            Storage storage,
            float flowRate,
            bool useSecondary)
        {
            consumer.conduitType = type;
            consumer.useSecondaryInput = useSecondary;
            consumer.storage = storage;
            consumer.capacityKG = storage.capacityKg;
            consumer.consumptionRate = flowRate;
            consumer.ignoreMinMassCheck = true;
            consumer.forceAlwaysSatisfied = true;
            consumer.alwaysConsume = true;
            consumer.keepZeroMassObject = true;
            consumer.wrongElementResult = ConduitConsumer.WrongElementResult.Store;
            consumer.capacityTag = GameTags.Any;
            consumer.isOn = true;
            consumer.isConsuming = true;
        }

        private static void ConfigureDispenser(
            ConduitDispenser dispenser,
            ConduitType type,
            Storage storage,
            bool useSecondary)
        {
            dispenser.conduitType = type;
            dispenser.useSecondaryOutput = useSecondary;
            dispenser.storage = storage;
            dispenser.elementFilter = null;
            dispenser.alwaysDispense = true;
            dispenser.isOn = true;
        }
    }
}
