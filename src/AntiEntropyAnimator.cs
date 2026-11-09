using UnityEngine;

namespace AntiEntropyGenerator
{
    /// <summary>
    /// Runtime animation controller: switches between the mechanical working loop and the
    /// powered-down state based on Operational.IsActive.
    /// </summary>
    public sealed class AntiEntropyAnimator : KMonoBehaviour
    {
        private const string WORKING_ANIM = "working";
        private const string OFF_ANIM = "off";

        private KBatchedAnimController anim;
        private Operational operational;

        protected override void OnSpawn()
        {
            base.OnSpawn();
            anim = GetComponent<KBatchedAnimController>();
            operational = GetComponent<Operational>();

            PlayCurrentState();
            Subscribe(824508782, OnActiveChanged);
        }

        private void OnActiveChanged(object data)
        {
            PlayCurrentState();
        }

        private void PlayCurrentState()
        {
            if (anim == null)
            {
                return;
            }

            bool active = operational != null && operational.IsActive;
            anim.Play(active ? WORKING_ANIM : OFF_ANIM, KAnim.PlayMode.Loop);
        }
    }
}
