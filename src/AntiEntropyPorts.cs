using UnityEngine;

namespace AntiEntropyGenerator
{
    /// <summary>
    /// Liquid/gas inputs for the Anti-Entropy Generator. Both inputs are registered as
    /// secondary inputs so they can coexist with the liquid/gas outputs on the same 4x3
    /// building.
    /// </summary>
    public sealed class AntiEntropyInputPorts : KMonoBehaviour, ISecondaryInput
    {
        // Offsets are relative to the building origin. For a 4-wide building the footprint
        // starts one cell left of the origin (PlacementOffsets -1..2).
        public ConduitPortInfo liquidInput =
            new ConduitPortInfo(ConduitType.Liquid, new CellOffset(-1, 0));

        public ConduitPortInfo gasInput =
            new ConduitPortInfo(ConduitType.Gas, new CellOffset(-1, 2));

        private Building building;
        private FlowUtilityNetwork.NetworkItem liquidItem;
        private FlowUtilityNetwork.NetworkItem gasItem;
        private int liquidCell = -1;
        private int gasCell = -1;

        public bool HasSecondaryConduitType(ConduitType type)
        {
            return type == liquidInput.conduitType || type == gasInput.conduitType;
        }

        public CellOffset GetSecondaryConduitOffset(ConduitType type)
        {
            if (type == liquidInput.conduitType)
            {
                return liquidInput.offset;
            }

            if (type == gasInput.conduitType)
            {
                return gasInput.offset;
            }

            return CellOffset.none;
        }

        protected override void OnSpawn()
        {
            base.OnSpawn();
            building = GetComponent<Building>();
            AddEndpoint(liquidInput, Endpoint.Sink, out liquidItem, out liquidCell);
            AddEndpoint(gasInput, Endpoint.Sink, out gasItem, out gasCell);
        }

        protected override void OnCleanUp()
        {
            RemoveEndpoint(liquidInput, ref liquidItem, ref liquidCell);
            RemoveEndpoint(gasInput, ref gasItem, ref gasCell);
            base.OnCleanUp();
        }

        private void AddEndpoint(
            ConduitPortInfo port,
            Endpoint endpointType,
            out FlowUtilityNetwork.NetworkItem item,
            out int cell)
        {
            item = null;
            cell = -1;
            if (building == null)
            {
                return;
            }

            cell = Grid.OffsetCell(building.NaturalBuildingCell(), port.offset);
            item = new FlowUtilityNetwork.NetworkItem(port.conduitType, endpointType, cell, gameObject);
            Conduit.GetNetworkManager(port.conduitType).AddToNetworks(cell, item, is_endpoint: true);
        }

        private void RemoveEndpoint(
            ConduitPortInfo port,
            ref FlowUtilityNetwork.NetworkItem item,
            ref int cell)
        {
            if (item == null)
            {
                return;
            }

            Conduit.GetNetworkManager(port.conduitType).RemoveFromNetworks(cell, item, is_endpoint: true);
            item = null;
            cell = -1;
        }
    }

    /// <summary>
    /// Liquid/gas outputs for the Anti-Entropy Generator. Both outputs are registered as
    /// secondary outputs.
    /// </summary>
    public sealed class AntiEntropyOutputPorts : KMonoBehaviour, ISecondaryOutput
    {
        public ConduitPortInfo liquidOutput =
            new ConduitPortInfo(ConduitType.Liquid, new CellOffset(2, 0));

        public ConduitPortInfo gasOutput =
            new ConduitPortInfo(ConduitType.Gas, new CellOffset(2, 2));

        private Building building;
        private FlowUtilityNetwork.NetworkItem liquidItem;
        private FlowUtilityNetwork.NetworkItem gasItem;
        private int liquidCell = -1;
        private int gasCell = -1;

        public bool HasSecondaryConduitType(ConduitType type)
        {
            return type == liquidOutput.conduitType || type == gasOutput.conduitType;
        }

        public CellOffset GetSecondaryConduitOffset(ConduitType type)
        {
            if (type == liquidOutput.conduitType)
            {
                return liquidOutput.offset;
            }

            if (type == gasOutput.conduitType)
            {
                return gasOutput.offset;
            }

            return CellOffset.none;
        }

        protected override void OnSpawn()
        {
            base.OnSpawn();
            building = GetComponent<Building>();
            AddEndpoint(liquidOutput, Endpoint.Source, out liquidItem, out liquidCell);
            AddEndpoint(gasOutput, Endpoint.Source, out gasItem, out gasCell);
        }

        protected override void OnCleanUp()
        {
            RemoveEndpoint(liquidOutput, ref liquidItem, ref liquidCell);
            RemoveEndpoint(gasOutput, ref gasItem, ref gasCell);
            base.OnCleanUp();
        }

        private void AddEndpoint(
            ConduitPortInfo port,
            Endpoint endpointType,
            out FlowUtilityNetwork.NetworkItem item,
            out int cell)
        {
            item = null;
            cell = -1;
            if (building == null)
            {
                return;
            }

            cell = Grid.OffsetCell(building.NaturalBuildingCell(), port.offset);
            item = new FlowUtilityNetwork.NetworkItem(port.conduitType, endpointType, cell, gameObject);
            Conduit.GetNetworkManager(port.conduitType).AddToNetworks(cell, item, is_endpoint: true);
        }

        private void RemoveEndpoint(
            ConduitPortInfo port,
            ref FlowUtilityNetwork.NetworkItem item,
            ref int cell)
        {
            if (item == null)
            {
                return;
            }

            Conduit.GetNetworkManager(port.conduitType).RemoveFromNetworks(cell, item, is_endpoint: true);
            item = null;
            cell = -1;
        }
    }
}
