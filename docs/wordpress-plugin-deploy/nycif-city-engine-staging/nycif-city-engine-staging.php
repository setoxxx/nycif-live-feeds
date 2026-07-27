<?php
/**
 * Plugin Name: NYCIF City Engine Staging
 * Description: Editor-only, draft-only bridge for reviewing a hash-pinned City Engine asset bundle. Source package only; do not install without separate approval.
 * Version: 0.1.0
 * Author: NYC In Focus
 * License: GPL-2.0-or-later
 * Text Domain: nycif-city-engine-staging
 */

if (!defined('ABSPATH')) {
    exit;
}

define('NYCIF_CITY_ENGINE_STAGING_VERSION', '0.1.0');
define('NYCIF_CITY_ENGINE_STAGING_SHORTCODE', 'nycif_city_engine_staging');
define('NYCIF_CITY_ENGINE_STAGING_PAGE_ID', 2865);
define('NYCIF_CITY_ENGINE_STAGING_CAPABILITY', 'edit_pages');
define('NYCIF_CITY_ENGINE_STAGING_MANIFEST', __DIR__ . '/assets/city-engine-staging-manifest.json');

/**
 * Return a generic fail-closed response that is safe for unauthorized readers.
 *
 * @return string
 */
function nycif_city_engine_staging_unavailable() {
    return '<div class="nycif-city-engine-staging-unavailable" role="status">'
        . esc_html__('This preview is not available.', 'nycif-city-engine-staging')
        . '</div>';
}

/**
 * Confirm that this request is an authenticated editor viewing the designated draft page.
 *
 * @return bool
 */
function nycif_city_engine_staging_request_is_authorized() {
    if (!is_user_logged_in() || !current_user_can(NYCIF_CITY_ENGINE_STAGING_CAPABILITY)) {
        return false;
    }

    if (!is_page(NYCIF_CITY_ENGINE_STAGING_PAGE_ID)) {
        return false;
    }

    return 'draft' === get_post_status(NYCIF_CITY_ENGINE_STAGING_PAGE_ID);
}

/**
 * Validate the local staging manifest and return the browser URL for the pinned bundle.
 *
 * The manifest may reference only a relative file beneath this plugin directory. Remote
 * origins, branches, mutable feed channels and parent-directory traversal are rejected.
 *
 * @return string|WP_Error
 */
function nycif_city_engine_staging_runtime_url() {
    if (!is_readable(NYCIF_CITY_ENGINE_STAGING_MANIFEST)) {
        return new WP_Error('nycif_staging_manifest_missing', 'Staging bundle manifest is not installed.');
    }

    $manifest_text = file_get_contents(NYCIF_CITY_ENGINE_STAGING_MANIFEST);
    $manifest = json_decode($manifest_text, true);
    if (!is_array($manifest)) {
        return new WP_Error('nycif_staging_manifest_invalid', 'Staging bundle manifest is invalid JSON.');
    }

    $required = array('schema_version', 'source_repository', 'source_commit', 'entrypoint', 'entrypoint_sha256');
    foreach ($required as $field) {
        if (!isset($manifest[$field]) || !is_string($manifest[$field]) || '' === trim($manifest[$field])) {
            return new WP_Error('nycif_staging_manifest_invalid', 'Staging bundle manifest is incomplete.');
        }
    }

    if ('setoxxx/nycif-web-platform' !== $manifest['source_repository']) {
        return new WP_Error('nycif_staging_source_rejected', 'Staging source repository is not approved.');
    }

    if (!preg_match('/^[0-9a-f]{40}$/', $manifest['source_commit'])) {
        return new WP_Error('nycif_staging_commit_rejected', 'Staging source commit is not immutable.');
    }

    $entrypoint = ltrim($manifest['entrypoint'], '/');
    if ('' === $entrypoint || false !== strpos($entrypoint, '..') || preg_match('#^[a-z][a-z0-9+.-]*://#i', $entrypoint)) {
        return new WP_Error('nycif_staging_path_rejected', 'Staging entrypoint must be a local relative path.');
    }

    $plugin_root = realpath(__DIR__);
    $entrypoint_path = realpath(__DIR__ . '/' . $entrypoint);
    if (!$plugin_root || !$entrypoint_path || 0 !== strpos($entrypoint_path, $plugin_root . DIRECTORY_SEPARATOR)) {
        return new WP_Error('nycif_staging_path_rejected', 'Staging entrypoint is outside the plugin package.');
    }

    $expected_hash = strtolower($manifest['entrypoint_sha256']);
    if (!preg_match('/^[0-9a-f]{64}$/', $expected_hash)) {
        return new WP_Error('nycif_staging_hash_rejected', 'Staging entrypoint hash is invalid.');
    }

    $actual_hash = hash_file('sha256', $entrypoint_path);
    if (!hash_equals($expected_hash, $actual_hash)) {
        return new WP_Error('nycif_staging_hash_mismatch', 'Staging entrypoint hash does not match the reviewed manifest.');
    }

    return plugins_url($entrypoint, __FILE__);
}

/**
 * Render the protected City Engine staging iframe.
 *
 * @return string
 */
function nycif_city_engine_staging_shortcode() {
    if (!nycif_city_engine_staging_request_is_authorized()) {
        return nycif_city_engine_staging_unavailable();
    }

    $runtime_url = nycif_city_engine_staging_runtime_url();
    if (is_wp_error($runtime_url)) {
        return '<div class="nycif-city-engine-staging-error" role="status">'
            . '<strong>' . esc_html__('City Engine staging is safely disabled.', 'nycif-city-engine-staging') . '</strong> '
            . esc_html($runtime_url->get_error_message())
            . '</div>';
    }

    return sprintf(
        '<section class="nycif-city-engine-staging" data-version="%1$s">'
        . '<p><strong>%2$s</strong> %3$s</p>'
        . '<iframe title="%4$s" src="%5$s" loading="eager" referrerpolicy="no-referrer" '
        . 'sandbox="allow-scripts allow-same-origin" allow="fullscreen" style="width:100%%;min-height:78vh;border:1px solid currentColor;border-radius:12px;"></iframe>'
        . '</section>',
        esc_attr(NYCIF_CITY_ENGINE_STAGING_VERSION),
        esc_html__('Protected staging preview.', 'nycif-city-engine-staging'),
        esc_html__('Visible only to authenticated editors on the designated draft page.', 'nycif-city-engine-staging'),
        esc_attr__('NYC In Focus City Engine staging preview', 'nycif-city-engine-staging'),
        esc_url($runtime_url)
    );
}
add_shortcode(NYCIF_CITY_ENGINE_STAGING_SHORTCODE, 'nycif_city_engine_staging_shortcode');
