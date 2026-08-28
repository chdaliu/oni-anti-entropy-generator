using System.Collections.Generic;
using HarmonyLib;
using KMod;
using UnityEngine;

namespace AntiEntropyGenerator
{
    public sealed class AntiEntropyGeneratorMod : UserMod2
    {
        public override void OnLoad(Harmony harmony)
        {
            base.OnLoad(harmony);
        }
    }

    /// <summary>
    /// The base game scans all loaded assemblies for IBuildingConfig implementations, so the
    /// building itself does not need to be registered manually. This patch only adds the
    /// localization strings, the build-menu entry, and the tech-tree unlock.
    /// </summary>
    [HarmonyPatch(typeof(GeneratedBuildings), nameof(GeneratedBuildings.LoadGeneratedBuildings))]
    public static class GeneratedBuildingsPatch
    {
        private static bool initialized;

        public static void Prefix()
        {
            if (initialized)
            {
                return;
            }

            initialized = true;
            LocString.CreateLocStringKeys(typeof(STRINGS), null);

            ModUtil.AddBuildingToPlanScreen(
                "Power",
                AntiEntropyGeneratorConfig.ID,
                "generators");

            TUNING.BUILDINGS.PLANSUBCATEGORYSORTING[AntiEntropyGeneratorConfig.ID] = "generators";

            // RenewableEnergy is the same tech group as the steam turbine (SteamTurbine2).
            // Add the ID before buildings are registered so BuildingDef.PostProcess can create
            // the matching TechItem.
            AddTechUnlock(Db.Get());
        }

        /// <summary>
        /// Also called from the Db.Initialize postfix so the tech ID exists regardless of
        /// whether the build-menu patch runs before or after building registration.
        /// </summary>
        public static void AddTechUnlock(Db db)
        {
            if (db == null || db.Techs == null)
            {
                return;
            }

            Tech tech = FindRenewableEnergyTech(db);
            if (tech == null)
            {
                Debug.LogWarning(
                    "[AntiEntropyGenerator] Could not find the RenewableEnergy tech; the building will not appear in the tech tree.");
                return;
            }

            if (!tech.unlockedItemIDs.Contains(AntiEntropyGeneratorConfig.ID))
            {
                tech.AddUnlockedItemIDs(AntiEntropyGeneratorConfig.ID);
            }
        }

        private static Tech FindRenewableEnergyTech(Db db)
        {
            var techs = db.Techs;
            Tech tech = techs.TryGet("RenewableEnergy");
            if (tech != null && tech.FoundNode)
            {
                return tech;
            }

            // Handle renamed/reordered tech trees or DLC combinations that use a different
            // research tree: find a tech that actually exists in the current tree and also
            // unlocks a steam turbine.
            for (int i = 0; i < techs.Count; i++)
            {
                Tech candidate = techs[i];
                if (candidate == null || !candidate.FoundNode)
                {
                    continue;
                }

                List<string> ids = candidate.unlockedItemIDs;
                if (ids.Contains("SteamTurbine2") || ids.Contains("SteamTurbine"))
                {
                    return candidate;
                }
            }

            return null;
        }
    }

    [HarmonyPatch(typeof(Db), nameof(Db.Initialize))]
    public static class DbInitializePatch
    {
        public static void Postfix(Db __instance)
        {
            GeneratedBuildingsPatch.AddTechUnlock(__instance);
        }
    }
}
