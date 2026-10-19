<?php

test('the application redirects guests to the login page', function () {
    $response = $this->get('/');

    $response->assertStatus(302);
    $response->assertRedirect(route('login', absolute: false));
});

test('cloudflare forwarded host and scheme are used for redirects', function () {
    $response = $this->withHeaders([
        'X-Forwarded-Host' => 'example.trycloudflare.com',
        'X-Forwarded-Port' => '443',
        'X-Forwarded-Proto' => 'https',
    ])->get('/');

    $response->assertRedirect('https://example.trycloudflare.com/login');
});
