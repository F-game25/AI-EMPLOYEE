"""Stripe payment integration for billing."""
import os
import logging
from typing import Optional, Dict, Any
import stripe
from datetime import datetime

logger = logging.getLogger(__name__)

# Initialize Stripe with API key from environment
stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
STRIPE_MODE = os.environ.get("STRIPE_MODE", "sandbox")  # sandbox or live


class StripePaymentManager:
    """Manage Stripe payments and subscriptions."""

    def __init__(self):
        if not stripe.api_key:
            logger.warning("STRIPE_API_KEY not set; Stripe integration disabled")
        self.mode = STRIPE_MODE

    def create_customer(self, tenant_id: str, email: str, name: str = "") -> Optional[str]:
        """Create a Stripe customer for a tenant."""
        if not stripe.api_key:
            logger.error("Stripe API key not configured")
            return None

        try:
            customer = stripe.Customer.create(
                email=email,
                name=name or "AI Employee Tenant",
                metadata={"tenant_id": tenant_id, "created_at": datetime.utcnow().isoformat()},
            )
            logger.info(f"Created Stripe customer for tenant {tenant_id}: {customer.id}")
            return customer.id
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            return None

    def create_payment_intent(
        self,
        customer_id: str,
        amount_cents: int,
        currency: str = "usd",
        description: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Create a payment intent for a one-time charge."""
        if not stripe.api_key:
            logger.error("Stripe API key not configured")
            return None

        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency,
                customer=customer_id,
                description=description,
                metadata={"mode": self.mode},
            )
            logger.info(f"Created payment intent: {intent.id}")
            return {
                "client_secret": intent.client_secret,
                "intent_id": intent.id,
                "amount": amount_cents,
                "currency": currency,
            }
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create payment intent: {e}")
            return None

    def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a subscription for a customer."""
        if not stripe.api_key:
            logger.error("Stripe API key not configured")
            return None

        try:
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id}],
                metadata=metadata or {},
            )
            logger.info(f"Created subscription: {subscription.id}")
            return {
                "subscription_id": subscription.id,
                "customer_id": customer_id,
                "status": subscription.status,
                "current_period_end": subscription.current_period_end,
                "next_billing_date": datetime.utcfromtimestamp(subscription.current_period_end).isoformat(),
            }
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create subscription: {e}")
            return None

    def get_subscription_status(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a subscription."""
        if not stripe.api_key:
            logger.error("Stripe API key not configured")
            return None

        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "customer_id": subscription.customer,
                "current_period_end": subscription.current_period_end,
                "next_billing_date": datetime.utcfromtimestamp(subscription.current_period_end).isoformat(),
                "items": [
                    {
                        "price_id": item.price.id,
                        "product_id": item.price.product,
                        "amount": item.price.unit_amount,
                        "currency": item.price.currency,
                    }
                    for item in subscription.items
                ],
            }
        except stripe.error.StripeError as e:
            logger.error(f"Failed to get subscription status: {e}")
            return None

    def cancel_subscription(self, subscription_id: str, at_period_end: bool = False) -> bool:
        """Cancel a subscription."""
        if not stripe.api_key:
            logger.error("Stripe API key not configured")
            return False

        try:
            if at_period_end:
                stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
            else:
                stripe.Subscription.delete(subscription_id)
            logger.info(f"Cancelled subscription: {subscription_id}")
            return True
        except stripe.error.StripeError as e:
            logger.error(f"Failed to cancel subscription: {e}")
            return False

    def get_invoice_pdf(self, invoice_id: str) -> Optional[str]:
        """Get the PDF URL for an invoice."""
        if not stripe.api_key:
            logger.error("Stripe API key not configured")
            return None

        try:
            invoice = stripe.Invoice.retrieve(invoice_id)
            return invoice.invoice_pdf
        except stripe.error.StripeError as e:
            logger.error(f"Failed to get invoice PDF: {e}")
            return None


def get_stripe_manager() -> StripePaymentManager:
    """Get global Stripe payment manager instance."""
    return StripePaymentManager()
