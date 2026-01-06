from flask import Blueprint, jsonify, request, session, redirect, url_for, flash
from models import User, db
from stripe_config import STRIPE_KEYS
import stripe
from datetime import datetime, timedelta

# Initialize Stripe
stripe.api_key = STRIPE_KEYS['secret_key']

payment = Blueprint('payment', __name__)

@payment.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    # Check if user is logged in
    if 'user_id' not in session:
        return jsonify({
            'redirect': url_for('login'),
            'message': 'Please log in to subscribe'
        }), 401

    # Check if user already has active subscription
    user = User.query.get(session['user_id'])
    if user and user.has_active_subscription:
        return jsonify({
            'error': 'You already have an active subscription',
            'redirect': url_for('chat')
        }), 400

    try:
        price_id = request.form.get('priceId')
        if not price_id:
            return jsonify({'error': 'Invalid price ID'}), 400

        checkout_session = stripe.checkout.Session.create(
            client_reference_id=str(session['user_id']),
            success_url=request.host_url + 'payment/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.host_url + 'payment/cancel',
            allow_promotion_codes=True,
            mode='subscription',
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }]
        )
        return jsonify({'checkoutUrl': checkout_session.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 403

@payment.route('/success')
def payment_success():
    session_id = request.args.get('session_id')
    if not session_id:
        return redirect(url_for('landing'))

    try:
        # Retrieve the checkout session
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        
        # Get subscription details
        subscription = stripe.Subscription.retrieve(checkout_session.subscription)
        
        # Update user's subscription status
        user = User.query.get(int(checkout_session.client_reference_id))
        if user:
            user.has_subscription = True
            # Set subscription end date based on the subscription period
            if subscription.plan.interval == 'month':
                user.subscription_end = datetime.utcnow() + timedelta(days=30)
            elif subscription.plan.interval == 'year':
                user.subscription_end = datetime.utcnow() + timedelta(days=365)
            else:  # 6-month plan
                user.subscription_end = datetime.utcnow() + timedelta(days=180)
            
            db.session.commit()
            flash('Subscription activated successfully!', 'success')
            
        return redirect(url_for('chat'))
    except Exception as e:
        flash('Error processing subscription', 'error')
        return redirect(url_for('landing'))

@payment.route('/cancel')
def payment_cancel():
    flash('Payment cancelled', 'warning')
    return redirect(url_for('landing'))