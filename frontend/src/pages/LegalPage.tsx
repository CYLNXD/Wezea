// ─── LegalPage — Mentions légales, CGV, CGU, Confidentialité, Cookies ──────────
import { useState } from 'react';
import { motion } from 'framer-motion';
import { Scale, Shield, ShoppingCart, FileText, Cookie } from 'lucide-react';
import { useLanguage } from '../i18n/LanguageContext';
import PageNavbar from '../components/PageNavbar';
import { analyticsOptIn, analyticsOptOut, getConsentStatus } from '../lib/analytics';

export type LegalSection = 'mentions' | 'confidentialite' | 'cgv' | 'cgu' | 'cookies';

interface Props {
  onBack:   () => void;
  section?: LegalSection;
  onGoClientSpace?: () => void;
  onGoHistory?: () => void;
  onGoAdmin?: () => void;
  onGoContact?: () => void;
}

const SECTIONS: { id: LegalSection; label: string; icon: React.ReactNode }[] = [
  { id: 'mentions',       label: 'Mentions légales',        icon: <Scale size={14} /> },
  { id: 'confidentialite',label: 'Confidentialité & RGPD',  icon: <Shield size={14} /> },
  { id: 'cgv',            label: 'CGV',                     icon: <ShoppingCart size={14} /> },
  { id: 'cgu',            label: 'CGU',                     icon: <FileText size={14} /> },
  { id: 'cookies',        label: 'Cookies',                 icon: <Cookie size={14} /> },
];

// ── Helpers de mise en forme ──────────────────────────────────────────────────

function H1({ children }: { children: React.ReactNode }) {
  return (
    <h1 className="text-xl font-black text-white mb-6 pb-3 border-b border-slate-700/60" style={{ letterSpacing: '-0.02em' }}>
      {children}
    </h1>
  );
}

function H2({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-sm font-bold text-cyan-400 uppercase tracking-widest mt-8 mb-3">
      {children}
    </h2>
  );
}

function P({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={`text-slate-300 text-sm leading-relaxed mb-3 ${className ?? ''}`}>{children}</p>;
}

function Li({ children }: { children: React.ReactNode }) {
  return (
    <li className="text-slate-300 text-sm leading-relaxed flex gap-2">
      <span className="text-cyan-500 shrink-0 mt-1">·</span>
      <span>{children}</span>
    </li>
  );
}

function Ul({ children }: { children: React.ReactNode }) {
  return <ul className="flex flex-col gap-1.5 mb-3 pl-1">{children}</ul>;
}

function Info({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-3 text-sm text-slate-300 leading-relaxed mb-4">
      {children}
    </div>
  );
}

function Warn({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-200 leading-relaxed mb-4">
      {children}
    </div>
  );
}

// ── Table simple ──────────────────────────────────────────────────────────────

function Table({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto mb-4 rounded-xl border border-slate-700/50">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-slate-800/80">
            {headers.map(h => (
              <th key={h} className="px-3 py-2.5 text-left text-slate-300 font-semibold border-b border-slate-700/50">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={i % 2 === 0 ? 'bg-slate-900/40' : 'bg-slate-800/30'}>
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-2.5 text-slate-300 border-b border-slate-700/20 align-top">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Sections ──────────────────────────────────────────────────────────────────

function Mentions() {
  return (
    <>
      <H1>Mentions légales</H1>
      <P>Conformément à la loi belge du 11 mars 2003 sur certains aspects juridiques des services de la société de l'information et au Code de droit économique, les présentes mentions légales s'appliquent au site <strong className="text-white">scan.wezea.net</strong>.</P>

      <H2>Éditeur du site</H2>
      <Table
        headers={['Information', 'Valeur']}
        rows={[
          ['Dénomination commerciale', 'WEZEA'],
          ['Responsable de la publication', 'Ceylan Top'],
          ['Statut juridique', 'Indépendant(e) en personne physique'],
          ['Numéro d\'entreprise (BCE)', '0811.380.056'],
          ['Numéro de TVA intracommunautaire', 'BE0811.380.056'],
          ['Adresse', 'Avenue Arthur Dezangré 32a, 1950 Kraainem, Belgique'],
          ['Email de contact', 'contact@wezea.net'],
        ]}
      />

      <H2>Hébergement</H2>
      <P><strong className="text-white">Hébergement principal :</strong></P>
      <Ul>
        <Li>Infomaniak Network SA — Rue Eugène-Marziano 25, 1227 Les Acacias, Genève, Suisse — <a href="https://www.infomaniak.com" className="text-cyan-400 hover:underline" target="_blank" rel="noreferrer">www.infomaniak.com</a></Li>
        <Li>Infrastructures on-premise exploitées par WEZEA, localisées en Belgique</Li>
      </Ul>

      <H2>Propriété intellectuelle</H2>
      <P>L'ensemble des éléments du site scan.wezea.net (textes, graphismes, logotypes, icônes, logiciels, rapports générés) sont protégés par le droit d'auteur belge et les conventions internationales en vigueur.</P>
      <P>Toute reproduction, représentation, modification ou exploitation, totale ou partielle, des contenus et services proposés sur ce site, sans l'accord préalable et écrit de WEZEA, est strictement interdite.</P>

      <H2>Limitation de responsabilité</H2>
      <P>WEZEA s'efforce de fournir des informations aussi précises et à jour que possible. Les analyses produites via le service scan.wezea.net reposent sur une analyse passive de l'empreinte publique des domaines et ne constituent pas un audit de sécurité complet (test d'intrusion, audit de code source, etc.).</P>
      <P>WEZEA ne saurait être tenu responsable des omissions, inexactitudes ou décisions prises sur la base des résultats obtenus via le service.</P>

      <H2>Droit applicable et juridiction compétente</H2>
      <P>Le présent site et ses conditions d'utilisation sont régis par le <strong className="text-white">droit belge</strong>. En cas de litige, et à défaut de résolution amiable, les tribunaux de l'arrondissement judiciaire de <strong className="text-white">Bruxelles</strong> seront seuls compétents.</P>

      <P className="text-slate-500 text-xs mt-8">Dernière mise à jour : {new Date().toLocaleDateString('fr-BE', { day: '2-digit', month: 'long', year: 'numeric' })}</P>
    </>
  );
}

function Confidentialite() {
  return (
    <>
      <H1>Politique de confidentialité & RGPD</H1>
      <P>WEZEA s'engage à protéger la vie privée de ses utilisateurs conformément au <strong className="text-white">Règlement général sur la protection des données (RGPD — UE 2016/679)</strong> et à la législation belge en vigueur.</P>

      <H2>Responsable du traitement</H2>
      <Info>
        <strong>Ceylan Top</strong>, exerçant sous la dénomination commerciale <strong>WEZEA</strong><br />
        Avenue Arthur Dezangré 32a, 1950 Kraainem, Belgique<br />
        Email : <a href="mailto:contact@wezea.net" className="text-cyan-400 hover:underline">contact@wezea.net</a>
      </Info>

      <H2>Données collectées et finalités</H2>
      <Table
        headers={['Catégorie', 'Données', 'Finalité', 'Base légale', 'Durée de conservation']}
        rows={[
          ['Compte utilisateur', 'Nom, prénom, adresse email', 'Création et gestion du compte', 'Exécution du contrat (art. 6.1.b)', 'Durée du compte + 3 ans'],
          ['Analyse de sécurité', 'Nom de domaine, résultats du scan, adresse IP', 'Fourniture du service d\'audit de sécurité', 'Exécution du contrat (art. 6.1.b)', '24 mois glissants'],
          ['Paiement', 'Référence transaction, plan souscrit (via Stripe)', 'Gestion des abonnements et facturation', 'Exécution du contrat (art. 6.1.b)', '10 ans (obligation comptable)'],
          ['Emails transactionnels', 'Adresse email', 'Envoi de rapports PDF et notifications', 'Exécution du contrat (art. 6.1.b)', 'Durée du compte'],
          ['Formulaire de contact', 'Nom, email, message', 'Traitement des demandes de support', 'Intérêt légitime (art. 6.1.f)', '3 ans'],
          ['Logs serveur', 'Adresse IP, horodatage, pages visitées', 'Sécurité et amélioration du service', 'Intérêt légitime (art. 6.1.f)', '12 mois'],
        ]}
      />

      <H2>Sous-traitants</H2>
      <P>WEZEA fait appel aux prestataires suivants qui traitent des données personnelles pour son compte :</P>
      <Table
        headers={['Prestataire', 'Rôle', 'Localisation', 'Garantie de transfert']}
        rows={[
          ['Stripe Inc.', 'Traitement des paiements', 'États-Unis', 'Clauses contractuelles types (UE)'],
          ['Brevo SAS (ex-Sendinblue)', 'Envoi d\'emails transactionnels', 'France (UE)', 'Adéquation (UE)'],
          ['Infomaniak Network SA', 'Hébergement de la plateforme', 'Suisse', 'Accord d\'adéquation CH-UE'],
          ['PostHog Inc.', 'Analyse anonyme de l\'usage (avec consentement)', 'États-Unis', 'Clauses contractuelles types (UE)'],
        ]}
      />

      <H2>Vos droits (RGPD)</H2>
      <P>Conformément au RGPD, vous disposez des droits suivants concernant vos données personnelles :</P>
      <Ul>
        <Li><strong className="text-white">Droit d'accès</strong> (art. 15) — obtenir une copie de vos données</Li>
        <Li><strong className="text-white">Droit de rectification</strong> (art. 16) — corriger des données inexactes</Li>
        <Li><strong className="text-white">Droit à l'effacement</strong> (art. 17) — demander la suppression de vos données</Li>
        <Li><strong className="text-white">Droit à la limitation</strong> (art. 18) — restreindre le traitement</Li>
        <Li><strong className="text-white">Droit à la portabilité</strong> (art. 20) — recevoir vos données dans un format structuré</Li>
        <Li><strong className="text-white">Droit d'opposition</strong> (art. 21) — vous opposer à certains traitements</Li>
      </Ul>
      <P>Pour exercer ces droits, contactez : <a href="mailto:contact@wezea.net" className="text-cyan-400 hover:underline">contact@wezea.net</a>. WEZEA s'engage à répondre dans un délai d'un mois.</P>

      <H2>Droit de recours</H2>
      <Info>
        Si vous estimez que le traitement de vos données porte atteinte à vos droits, vous pouvez introduire une plainte auprès de l'<strong>Autorité de Protection des Données (APD)</strong> :<br />
        Rue de la Presse 35, 1000 Bruxelles — <a href="https://www.autoriteprotectiondonnees.be" className="text-cyan-400 hover:underline" target="_blank" rel="noreferrer">www.autoriteprotectiondonnees.be</a> — +32 (0)2 274 48 00
      </Info>

      <H2>Sécurité des données</H2>
      <P>WEZEA met en œuvre des mesures techniques et organisationnelles appropriées pour protéger vos données : chiffrement TLS en transit, accès restreints par authentification, journalisation des accès, sauvegardes régulières.</P>

      <H2>Cookies</H2>
      <P>Pour plus d'informations sur les cookies utilisés, consultez notre <strong className="text-white">Politique Cookies</strong>.</P>

      <P className="text-slate-500 text-xs mt-8">Dernière mise à jour : {new Date().toLocaleDateString('fr-BE', { day: '2-digit', month: 'long', year: 'numeric' })}</P>
    </>
  );
}

function CGV() {
  return (
    <>
      <H1>Conditions Générales de Vente (CGV)</H1>
      <Warn>
        ⚠️ Ces CGV s'appliquent uniquement aux abonnements payants (Plan Starter et Plan Pro). L'utilisation du Plan Free est régie uniquement par les CGU.
      </Warn>

      <H2>Parties contractantes</H2>
      <P>Les présentes CGV régissent les relations contractuelles entre :</P>
      <Ul>
        <Li><strong className="text-white">WEZEA</strong> (Ceylan Top, indépendant(e) en personne physique, BCE 0811.380.056, Avenue Arthur Dezangré 32a, 1950 Kraainem, Belgique) — ci-après « le Prestataire »</Li>
        <Li>Toute personne physique ou morale ayant souscrit un abonnement payant — ci-après « le Client »</Li>
      </Ul>

      <H2>Description des services</H2>
      <Table
        headers={['Plan', 'Description', 'Facturation']}
        rows={[
          ['Free', 'Accès limité au service d\'audit passif (quota hebdomadaire restreint)', 'Gratuit'],
          ['Starter', 'Scans illimités, rapports PDF, historique des scans, espace client', 'Mensuel ou annuel'],
          ['Pro', 'Toutes fonctionnalités Starter + sous-domaines, CVE, monitoring avancé', 'Mensuel ou annuel'],
        ]}
      />
      <P>Les fonctionnalités détaillées et les tarifs en vigueur sont consultables sur le site scan.wezea.net. WEZEA se réserve le droit de modifier les tarifs avec un préavis de 30 jours.</P>

      <H2>Prix et TVA</H2>
      <P>Les prix sont exprimés en <strong className="text-white">euros (EUR)</strong>. WEZEA applique le régime TVA forfaitaire conformément à la législation fiscale belge en vigueur. Pour toute question relative à la facturation, contactez contact@wezea.net.</P>

      <H2>Modalités de paiement</H2>
      <Ul>
        <Li>Le paiement est sécurisé et traité par <strong className="text-white">Stripe Inc.</strong> (carte bancaire, SEPA)</Li>
        <Li>WEZEA ne stocke aucune donnée bancaire sur ses serveurs</Li>
        <Li>En cas d'échec de paiement ou de rétrofacturation (chargeback), l'accès aux fonctionnalités payantes est suspendu immédiatement</Li>
        <Li>Les abonnements sont renouvelés automatiquement sauf résiliation préalable</Li>
      </Ul>

      <H2>Droit de rétractation (B2C)</H2>
      <Info>
        Conformément aux articles VI.47 et suivants du <strong>Code de droit économique belge</strong>, tout consommateur (personne physique agissant hors cadre professionnel) dispose d'un délai de <strong>14 jours calendrier</strong> à compter de la souscription pour exercer son droit de rétractation sans justification ni pénalité.
      </Info>
      <P>Toutefois, en application de l'article VI.53, 13° du Code de droit économique, <strong className="text-white">le droit de rétractation ne s'applique pas</strong> si :</P>
      <Ul>
        <Li>Le Client a expressément demandé l'exécution immédiate du service avant l'expiration du délai de rétractation</Li>
        <Li>Le Client a reconnu perdre son droit de rétractation dès lors que le contrat est pleinement exécuté</Li>
      </Ul>
      <P>Cette renonciation est matérialisée par la case à cocher lors de la souscription. <strong className="text-white">Les clients professionnels (B2B) ne bénéficient pas du droit de rétractation.</strong></P>

      <H2>Résiliation et remboursements</H2>
      <Ul>
        <Li>Résiliation possible à tout moment depuis l'espace client, avec effet à la fin de la période de facturation en cours</Li>
        <Li>Aucun remboursement prorata temporis n'est accordé sauf obligation légale</Li>
        <Li>En cas de résiliation par WEZEA pour manquement aux CGU, aucun remboursement n'est dû</Li>
      </Ul>

      <H2>Responsabilité du Prestataire</H2>
      <P>WEZEA est tenu à une <strong className="text-white">obligation de moyens</strong>. Les analyses produites sont basées sur une analyse passive de l'empreinte publique et ne constituent pas un audit de sécurité exhaustif. WEZEA ne saurait être tenu responsable des dommages directs ou indirects résultant de l'utilisation ou de la non-utilisation des résultats fournis.</P>
      <P>La responsabilité de WEZEA est limitée au montant des sommes effectivement versées par le Client au cours des 12 derniers mois.</P>

      <H2>Médiation et règlement des litiges</H2>
      <P>En cas de litige, le Client consommateur peut recourir gratuitement au <strong className="text-white">Service de Médiation pour le Consommateur</strong> : <a href="https://www.mediationconsommateur.be" className="text-cyan-400 hover:underline" target="_blank" rel="noreferrer">www.mediationconsommateur.be</a>.</P>
      <P>Les présentes CGV sont soumises au <strong className="text-white">droit belge</strong>. Tout litige non résolu à l'amiable sera soumis aux tribunaux de l'arrondissement judiciaire de Bruxelles.</P>

      <P className="text-slate-500 text-xs mt-8">Dernière mise à jour : {new Date().toLocaleDateString('fr-BE', { day: '2-digit', month: 'long', year: 'numeric' })}</P>
    </>
  );
}

function CGU() {
  return (
    <>
      <H1>Conditions Générales d'Utilisation (CGU)</H1>
      <P>L'accès et l'utilisation du site <strong className="text-white">scan.wezea.net</strong> impliquent l'acceptation pleine et entière des présentes Conditions Générales d'Utilisation.</P>

      <H2>Objet du service</H2>
      <P>WEZEA propose un service d'analyse passive de l'empreinte publique de sécurité des domaines internet. Le service examine les configurations DNS, SSL/TLS, les en-têtes HTTP, l'exposition des ports et les listes noires, sans interaction intrusive avec les systèmes analysés.</P>

      <H2>Accès au service</H2>
      <P>WEZEA s'efforce d'assurer la disponibilité du service 24h/24 et 7j/7. Des interruptions peuvent survenir pour maintenance, mises à jour de sécurité ou incidents techniques. WEZEA ne peut être tenu responsable des indisponibilités ponctuelles.</P>

      <H2>Utilisation autorisée</H2>
      <Warn>
        ⚠️ L'utilisateur s'engage à n'analyser que des domaines dont il est <strong>propriétaire</strong> ou pour lesquels il dispose d'une <strong>autorisation explicite et écrite</strong> du propriétaire.
      </Warn>
      <P>L'utilisateur s'engage à :</P>
      <Ul>
        <Li>Ne pas utiliser le service à des fins illicites, malveillantes ou frauduleuses</Li>
        <Li>Ne pas tenter de contourner les mesures de sécurité, les limitations d'accès ou les quotas</Li>
        <Li>Ne pas effectuer d'actions susceptibles de perturber ou de surcharger l'infrastructure de WEZEA</Li>
        <Li>Ne pas revendre, redistribuer ou exploiter commercialement les résultats sans accord écrit de WEZEA</Li>
        <Li>Ne pas utiliser le service pour collecter des informations à des fins de cyberattaque ou d'espionnage industriel</Li>
      </Ul>
      <Info>
        L'utilisation du service sur un domaine tiers sans autorisation peut constituer une infraction à la <strong>loi belge du 28 novembre 2000 relative à la criminalité informatique</strong> (art. 550bis du Code pénal) et être passible de poursuites pénales.
      </Info>

      <H2>Comptes utilisateurs</H2>
      <Ul>
        <Li>L'utilisateur est responsable de la confidentialité de ses identifiants de connexion</Li>
        <Li>Toute activité effectuée depuis un compte est réputée être le fait de son titulaire</Li>
        <Li>En cas de compromission du compte, l'utilisateur doit en informer WEZEA sans délai à contact@wezea.net</Li>
        <Li>WEZEA se réserve le droit de suspendre ou résilier tout compte en cas de violation des présentes CGU</Li>
      </Ul>

      <H2>Propriété intellectuelle des rapports</H2>
      <P>Les rapports PDF générés par le service sont destinés à l'usage personnel ou professionnel interne de l'utilisateur. Toute publication, revente ou diffusion publique des rapports est interdite sans accord préalable et écrit de WEZEA.</P>

      <H2>Limitation de responsabilité</H2>
      <P>Les résultats fournis par le service sont indicatifs et basés sur une analyse passive. Ils ne se substituent pas à un audit de sécurité professionnel. L'utilisateur est seul responsable des décisions prises sur la base des résultats obtenus.</P>

      <H2>Modification des CGU</H2>
      <P>WEZEA se réserve le droit de modifier les présentes CGU à tout moment. Les utilisateurs disposant d'un compte seront informés par email en cas de modification substantielle, avec un préavis de 15 jours. La poursuite de l'utilisation du service après modification vaut acceptation des nouvelles CGU.</P>

      <H2>Droit applicable</H2>
      <P>Les présentes CGU sont régies par le <strong className="text-white">droit belge</strong>. Tout litige sera soumis aux juridictions compétentes de l'arrondissement judiciaire de Bruxelles.</P>

      <P className="text-slate-500 text-xs mt-8">Dernière mise à jour : {new Date().toLocaleDateString('fr-BE', { day: '2-digit', month: 'long', year: 'numeric' })}</P>
    </>
  );
}

function Cookies() {
  const [consent, setConsent] = useState<'accepted' | 'declined' | null>(getConsentStatus);

  function handleAccept() {
    analyticsOptIn();
    setConsent('accepted');
  }

  function handleDecline() {
    analyticsOptOut();
    setConsent('declined');
  }

  return (
    <>
      <H1>Politique de gestion des cookies</H1>
      <P>Conformément à la directive ePrivacy (2002/58/CE) et au RGPD, la présente politique explique l'utilisation des cookies sur le site <strong className="text-white">scan.wezea.net</strong>.</P>

      <H2>Qu'est-ce qu'un cookie ?</H2>
      <P>Un cookie est un petit fichier texte déposé sur votre terminal (ordinateur, tablette, smartphone) lors de la visite d'un site web. Il permet de mémoriser des informations relatives à votre navigation.</P>

      <H2>Cookies strictement nécessaires</H2>
      <P>Ces cookies sont indispensables au fonctionnement du service. Ils ne nécessitent pas votre consentement.</P>
      <Table
        headers={['Nom du cookie', 'Finalité', 'Durée', 'Tiers']}
        rows={[
          ['wezea_token', 'Jeton d\'authentification JWT — maintien de la session utilisateur', 'Session navigateur', 'Non'],
          ['wezea_client_id', 'Identifiant client anonyme — gestion des quotas de scans et prévention des abus', '1 an', 'Non'],
        ]}
      />
      <Warn>
        La désactivation de ces cookies empêche la connexion au service et le maintien de votre session.
      </Warn>

      <H2>Cookies analytiques et de performance</H2>
      <P>Ces cookies ne sont déposés qu'après <strong className="text-white">votre consentement explicite</strong> via le bandeau d'information qui s'affiche lors de votre première visite.</P>
      <Table
        headers={['Outil', 'Finalité', 'Durée', 'Données transmises']}
        rows={[
          ['PostHog (posthog.com)', 'Analyse anonyme de l\'usage du scanner (pages vues, actions réalisées, funnel de conversion) — aucune donnée revendue, aucun profilage publicitaire', '12 mois', 'Pages visitées, actions anonymisées, identifiant de session'],
        ]}
      />
      <Info>
        WEZEA n'utilise pas Google Analytics, Facebook Pixel ou tout autre outil de traçage publicitaire tiers. Les données analytiques collectées via PostHog sont strictement limitées à l'amélioration du service.
      </Info>
      <P>
        Vous pouvez retirer votre consentement à tout moment en cliquant sur le lien ci-dessous. Vos préférences sont enregistrées dans votre navigateur (<code>localStorage</code>) et n'expirent pas automatiquement.
      </P>

      <H2>Cookies de paiement (Stripe)</H2>
      <P>Lors du processus de paiement, Stripe Inc. peut déposer des cookies techniques sur votre terminal pour la sécurisation des transactions. Ces cookies sont strictement nécessaires à l'exécution du contrat et sont régis par la <a href="https://stripe.com/fr/privacy" className="text-cyan-400 hover:underline" target="_blank" rel="noreferrer">politique de confidentialité de Stripe</a>.</P>

      <H2>Votre consentement actuel</H2>
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 px-4 py-3 mb-4 flex flex-wrap items-center gap-3">
        <span className="text-sm text-slate-300 flex-1">
          {consent === 'accepted' && <><span className="text-green-400 font-semibold">✓ Accepté</span> — les cookies analytiques PostHog sont actifs.</>}
          {consent === 'declined' && <><span className="text-amber-400 font-semibold">✗ Refusé</span> — aucun cookie analytique n'est déposé.</>}
          {consent === null       && <><span className="text-slate-400">Non défini</span> — vous n'avez pas encore fait de choix.</>}
        </span>
        <div className="flex gap-2 flex-shrink-0">
          {consent !== 'declined' && (
            <button
              onClick={handleDecline}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-600/60 text-slate-400 hover:text-slate-300 hover:border-slate-500/70 transition-all"
            >
              Refuser
            </button>
          )}
          {consent !== 'accepted' && (
            <button
              onClick={handleAccept}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/30 transition-all"
            >
              Accepter
            </button>
          )}
        </div>
      </div>

      <H2>Gestion de vos préférences</H2>
      <P>Vous pouvez à tout moment gérer, désactiver ou supprimer les cookies via les paramètres de votre navigateur :</P>
      <Ul>
        <Li><strong className="text-white">Google Chrome</strong> : Paramètres → Confidentialité et sécurité → Cookies</Li>
        <Li><strong className="text-white">Mozilla Firefox</strong> : Paramètres → Vie privée et sécurité → Cookies</Li>
        <Li><strong className="text-white">Safari</strong> : Préférences → Confidentialité → Bloquer les cookies</Li>
        <Li><strong className="text-white">Microsoft Edge</strong> : Paramètres → Confidentialité, recherche et services → Cookies</Li>
      </Ul>
      <P>Vous pouvez également supprimer les cookies déjà déposés via les mêmes menus de paramètres.</P>

      <H2>Contact</H2>
      <P>Pour toute question relative à notre utilisation des cookies : <a href="mailto:contact@wezea.net" className="text-cyan-400 hover:underline">contact@wezea.net</a></P>

      <P className="text-slate-500 text-xs mt-8">Dernière mise à jour : {new Date().toLocaleDateString('fr-BE', { day: '2-digit', month: 'long', year: 'numeric' })}</P>
    </>
  );
}

// ── Composant principal ───────────────────────────────────────────────────────

export default function LegalPage({ onBack, section = 'mentions', onGoClientSpace, onGoHistory, onGoAdmin, onGoContact }: Props) {
  const { lang } = useLanguage();
  const [active, setActive] = useState<LegalSection>(section);

  const content: Record<LegalSection, React.ReactNode> = {
    mentions:        <Mentions />,
    confidentialite: <Confidentialite />,
    cgv:             <CGV />,
    cgu:             <CGU />,
    cookies:         <Cookies />,
  };

  return (
    <div className="relative min-h-screen text-slate-100">
      {/* Grille cyber — identique au hero Dashboard */}
      <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: 'linear-gradient(rgba(34,211,238,1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)', backgroundSize: '48px 48px', opacity: 0.025 }} />

      {/* Nav */}
      <PageNavbar
        onBack={onBack}
        title={lang === 'fr' ? 'Informations légales' : 'Legal information'}
        icon={<Scale size={14} />}
        onGoClientSpace={onGoClientSpace}
        onGoHistory={onGoHistory}
        onGoAdmin={onGoAdmin}
        onGoContact={onGoContact}
      />

      <div className="max-w-4xl mx-auto px-4 py-8">

        {/* Tabs */}
        <div className="flex flex-wrap gap-2 mb-8">
          {SECTIONS.map(s => (
            <button
              key={s.id}
              onClick={() => setActive(s.id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold transition-all ${
                active === s.id ? 'text-cyan-300' : 'text-slate-400 hover:text-slate-200'
              }`}
              style={active === s.id ? {
                background: 'linear-gradient(180deg,rgba(34,211,238,0.12),rgba(34,211,238,0.06))',
                border: '1px solid rgba(34,211,238,0.3)',
                boxShadow: '0 2px 8px rgba(34,211,238,0.08), 0 1px 0 rgba(255,255,255,0.05) inset',
              } : {
                background: 'linear-gradient(180deg,rgba(255,255,255,0.03),rgba(0,0,0,0.06))',
                border: '1px solid rgba(255,255,255,0.07)',
                boxShadow: 'var(--shadow-btn)',
              }}
            >
              {s.icon}
              {s.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <motion.div
          key={active}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className="sku-panel rounded-2xl p-6 sm:p-8"
        >
          {content[active]}
        </motion.div>

        {/* Footer légal */}
        <p className="text-center text-slate-600 text-xs mt-8">
          WEZEA · BCE 0811.380.056 · Avenue Arthur Dezangré 32a, 1950 Kraainem, Belgique · <a href="mailto:contact@wezea.net" className="hover:text-slate-400 transition-colors">contact@wezea.net</a>
        </p>

      </div>
    </div>
  );
}
